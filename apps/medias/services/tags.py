"""Tags of the medias: parsing, normalization and assignment.

Tags belong to the user (``created_by``) and are unique per user whatever their case.
"""

from typing import TYPE_CHECKING, Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet

from ..models import Media, MediaTag

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from inspections.models import InspectionFolder

MAX_TAGS_PER_MEDIA = 10
MAX_TAG_LENGTH = 50


def parse_tag_names(raw: str) -> list[str]:
    """Split the text typed in the "new tags" field.

    Args:
        raw: Tags separated by commas or semicolons.

    Returns:
        The non-empty names, with their spaces collapsed.
    """
    names = raw.replace(";", ",").split(",")
    return [" ".join(name.split()) for name in names if name.strip()]


def normalize_tag_names(names: Iterable[str]) -> list[str]:
    """Remove the duplicates (case-insensitive) and check the limits.

    Args:
        names: Tag names, the first spelling of a duplicate is kept.

    Returns:
        The distinct names.

    Raises:
        ValidationError: If a name is too long or there are too many tags.
    """
    distinct: dict[str, str] = {}
    for name in names:
        if len(name) > MAX_TAG_LENGTH:
            raise ValidationError(
                f"Un tag ne peut pas dépasser {MAX_TAG_LENGTH} caractères."
            )
        distinct.setdefault(name.lower(), name)
    if len(distinct) > MAX_TAGS_PER_MEDIA:
        raise ValidationError(
            f"Un média ne peut pas avoir plus de {MAX_TAGS_PER_MEDIA} tags."
        )
    return list(distinct.values())


def set_media_tags(media: Media, user: "CustomUser", names: Iterable[str]) -> None:
    """Replace the tags of a media, creating the ones the user does not have yet.

    Args:
        media: Media to tag.
        user: Owner of the tags.
        names: Names of the tags the media must have.

    Raises:
        ValidationError: If a name is too long or there are too many tags.
    """
    names = normalize_tag_names(names)
    with transaction.atomic():
        tags = [
            MediaTag.objects.get_or_create(
                created_by=user,
                name__iexact=name,
                defaults={"name": name, "updated_by": user},
            )[0]
            for name in names
        ]
        media.tags.set(tags)


def get_user_tags(user: "CustomUser") -> QuerySet[MediaTag]:
    """Return the tags of the user that are used by at least one media.

    Args:
        user: Owner of the tags.

    Returns:
        The tags, sorted by name.
    """
    return MediaTag.objects.filter(created_by=user, medias__isnull=False).distinct()


def get_folder_tags(
    folder: "InspectionFolder", user: "CustomUser"
) -> QuerySet[MediaTag]:
    """Return the tags used by the medias of a folder.

    Args:
        folder: Folder of the medias.
        user: Owner of the folder and of the tags.

    Returns:
        The tags, sorted by name.
    """
    return MediaTag.objects.filter(created_by=user, medias__folder=folder).distinct()
