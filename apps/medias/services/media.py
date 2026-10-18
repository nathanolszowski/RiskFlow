"""Business logic of the medias: ownership, listing, creation, quota and archiving.

Every query goes through the owner of the folder (``folder__created_by``), like the
visits and recommendations.
"""

import os
from typing import TYPE_CHECKING, Any, Optional

from core.services import (
    archive_tracked_instance,
    delete_archived_instance,
    unarchive_tracked_instance,
    update_tracked_instance,
)
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q, QuerySet, Sum
from django.shortcuts import get_object_or_404

from ..models import Media
from .images import process_image
from .tags import normalize_tag_names, set_media_tags
from .validation import validate_upload

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from inspections.models import InspectionFolder, Recommandation, VisitInstance

QUOTA_WARNING_PERCENT = 80


def get_media_by_id(pk: int, user: "CustomUser") -> Media:
    """Return a media of the user, or raise a 404.

    Args:
        pk: Primary key of the media.
        user: Owner of the folder of the media.

    Returns:
        The media, with its folder, visit and recommendation.

    Raises:
        Http404: If the media does not exist or belongs to another user.
    """
    return get_object_or_404(
        Media.objects.select_related("folder", "visit", "recommandation"),
        pk=pk,
        folder__created_by=user,
    )


def get_filtered_medias(
    folder: "InspectionFolder",
    user: "CustomUser",
    *,
    q: str = "",
    media_type: str = "",
    target: str = "",
    tag: str = "",
    status: str = "active",
) -> QuerySet[Media]:
    """List the medias of a folder with the filters of the tab.

    Args:
        folder: Folder of the medias.
        user: Owner of the folder.
        q: Text searched in the caption, the original name, the notes and the tags.
        media_type: One of ``Media.MediaType`` values, empty for all.
        target: ``folder`` (not attached), ``visit:<pk>`` or ``recommandation:<pk>``;
            empty for all.
        tag: Name of a tag, empty for all.
        status: ``active`` or ``archived``.

    Returns:
        The medias, newest first.
    """
    medias = (
        Media.objects.filter(
            folder=folder, folder__created_by=user, is_active=(status != "archived")
        )
        .select_related("visit", "recommandation", "created_by")
        .prefetch_related("tags")
    )
    if q:
        medias = medias.filter(
            Q(title__icontains=q)
            | Q(original_name__icontains=q)
            | Q(notes__icontains=q)
            | Q(tags__name__icontains=q)
        ).distinct()
    if tag:
        medias = medias.filter(tags__name__iexact=tag)
    if media_type in Media.MediaType.values:
        medias = medias.filter(media_type=media_type)
    if target == "folder":
        medias = medias.filter(visit__isnull=True, recommandation__isnull=True)
    elif target.startswith("visit:") and target[6:].isdigit():
        medias = medias.filter(visit_id=int(target[6:]))
    elif target.startswith("recommandation:") and target[15:].isdigit():
        medias = medias.filter(recommandation_id=int(target[15:]))
    return medias


def get_folder_usage(folder: "InspectionFolder") -> dict[str, Any]:
    """Return the storage used by a folder against its approximate quota.

    Archived medias count: they stay in the storage until they are deleted.

    Args:
        folder: Folder to measure.

    Returns:
        ``used_bytes``, ``quota_bytes``, ``percent`` (capped at 100, for the bar),
        ``remaining_bytes`` and ``level`` (``normal``, ``warning`` or ``full``).
    """
    used = (
        Media.objects.filter(folder=folder).aggregate(total=Sum("size"))["total"] or 0
    )
    quota = settings.MEDIA_FOLDER_QUOTA_MB * 1024 * 1024
    raw_percent = used * 100 / quota if quota else 100
    if raw_percent >= 100:
        level = "full"
    elif raw_percent >= QUOTA_WARNING_PERCENT:
        level = "warning"
    else:
        level = "normal"
    return {
        "used_bytes": used,
        "quota_bytes": quota,
        "remaining_bytes": max(quota - used, 0),
        "percent": min(int(raw_percent), 100),
        "level": level,
    }


def create_media(
    folder: "InspectionFolder",
    user: "CustomUser",
    uploaded: UploadedFile,
    *,
    visit: Optional["VisitInstance"] = None,
    recommandation: Optional["Recommandation"] = None,
    title: str = "",
    notes: str = "",
    tags: Optional[list[str]] = None,
) -> Media:
    """Validate, compress (images) and store an uploaded file.

    Args:
        folder: Folder the media belongs to.
        user: User uploading the file.
        uploaded: File received from the form.
        visit: Optional visit to attach the media to.
        recommandation: Optional recommendation to attach the media to.
        title: Optional caption.
        notes: Optional notes.
        tags: Names of the tags to put on the media.

    Returns:
        The saved media.

    Raises:
        ValidationError: If the file is refused, the target does not belong to the
            folder, the tags are invalid, or the quota of the folder would be exceeded.
    """
    tag_names = normalize_tag_names(tags or [])
    original_name = "".join(
        c for c in os.path.basename(uploaded.name or "") if c.isprintable()
    )[:255]
    media_type, content_type = validate_upload(uploaded)

    media = Media(
        folder=folder,
        visit=visit,
        recommandation=recommandation,
        original_name=original_name,
        media_type=media_type,
        title=title,
        notes=notes,
        created_by=user,
        updated_by=user,
    )
    media.clean()

    # Read once, before the costly image processing: a full folder refuses right away
    remaining = get_folder_usage(folder)["remaining_bytes"]
    if remaining <= 0:
        raise ValidationError(
            "Quota du dossier atteint : supprimez des médias pour en ajouter."
        )

    thumbnail = None
    if media_type == Media.MediaType.IMAGE:
        processed = process_image(uploaded)
        stored, thumbnail, content_type = (
            processed.image,
            processed.thumbnail,
            processed.content_type,
        )
        media.metadata = processed.metadata
        size = stored.size
    else:
        stored, size = uploaded, uploaded.size

    if size > remaining:
        raise ValidationError(
            "Quota du dossier dépassé : supprimez des médias ou réduisez ce fichier."
        )

    media.content_type = content_type
    media.size = size
    media.file.save(stored.name, stored, save=False)
    if thumbnail:
        media.thumbnail.save(thumbnail.name, thumbnail, save=False)
    try:
        media.save()
    except Exception:
        # The row was not created: do not leave orphan files in the storage
        media.file.storage.delete(media.file.name)
        if media.thumbnail:
            media.thumbnail.storage.delete(media.thumbnail.name)
        raise
    set_media_tags(media, user, tag_names)
    return media


def update_media(
    media: Media,
    user: "CustomUser",
    *,
    tags: Optional[list[str]] = None,
    **fields: Any,
) -> Media:
    """Update the caption, the notes, the target or the tags of a media.

    Args:
        media: Media to update.
        user: User performing the update.
        tags: Names of the tags the media must have, None to leave them as they are.
        **fields: New values among ``title``, ``notes``, ``visit`` and ``recommandation``.

    Returns:
        The updated media.

    Raises:
        ValidationError: If the new target does not belong to the folder or the tags
            are invalid.
    """
    for name, value in fields.items():
        setattr(media, name, value)
    media.clean()
    if tags is not None:
        tags = normalize_tag_names(tags)
    media = update_tracked_instance(media, user, **fields)
    if tags is not None:
        set_media_tags(media, user, tags)
    return media


def archive_media(media: Media, user: "CustomUser") -> Media:
    """Archive a media (soft delete).

    Args:
        media: Media to archive.
        user: User performing the action.

    Returns:
        The archived media.
    """
    return archive_tracked_instance(media, user)


def unarchive_media(media: Media, user: "CustomUser") -> Media:
    """Restore an archived media.

    Args:
        media: Media to restore.
        user: User performing the action.

    Returns:
        The restored media.
    """
    return unarchive_tracked_instance(media, user)


def delete_media(media: Media) -> None:
    """Permanently delete an archived media; the signal removes its files.

    Args:
        media: Archived media to delete.

    Raises:
        ValueError: If the media is still active.
    """
    delete_archived_instance(media)
