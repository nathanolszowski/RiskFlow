"""Models of the medias app: files attached to a folder, a visit or a recommendation."""

import os
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from core.models import TrackingModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

if TYPE_CHECKING:
    pass


def media_upload_to(instance: "Media", filename: str) -> str:
    """Return the storage path of a file: a random name, never the original one.

    Args:
        instance: Media the file belongs to.
        filename: Name of the uploaded file, only its extension is kept.

    Returns:
        The path relative to the storage root.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"folders/{instance.folder_id}/{uuid.uuid4().hex}{ext}"


def thumbnail_upload_to(instance: "Media", filename: str) -> str:
    """Return the storage path of a thumbnail.

    Args:
        instance: Media the thumbnail belongs to.
        filename: Name of the thumbnail, only its extension is kept.

    Returns:
        The path relative to the storage root.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"folders/{instance.folder_id}/thumbnails/{uuid.uuid4().hex}{ext}"


class MediaTag(TrackingModel):
    """Free label of a user, to sort and find medias.

    Tags are unique per user whatever their case, and are created on the fly when a
    media is tagged.

    Attributes:
        name: Text of the tag.
    """

    name = models.CharField(max_length=50, verbose_name="Nom")

    class Meta(TrackingModel.Meta):
        verbose_name = "Tag de média"
        verbose_name_plural = "Tags de média"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "created_by", name="mediatag_unique_name_per_user"
            )
        ]

    def __str__(self) -> str:
        """Return the name of the tag."""
        return self.name


class Media(TrackingModel):
    """File attached to an inspection folder, and optionally to one of its visits or recommendations.

    The folder is always set: it carries the ownership (``folder__created_by``).
    ``visit`` and ``recommandation`` are exclusive and must belong to the same folder.
    Deleting a visit or a recommendation keeps its medias on the folder (``SET_NULL``);
    only deleting the folder deletes them.

    Attributes:
        folder: Folder the media belongs to.
        visit: Optional visit the media is attached to.
        recommandation: Optional recommendation the media is attached to.
        file: Stored file (images are compressed before being stored).
        thumbnail: Thumbnail, for images only.
        original_name: Name of the uploaded file.
        content_type: MIME type deduced from the extension.
        media_type: Family of the file, see ``MediaType``.
        size: Size in bytes of the stored file.
        metadata: EXIF data of a photo (capture date, GPS position, camera).
        tags: Free labels of the user.
        title: Optional caption.
        notes: Optional notes.
    """

    class MediaType(models.TextChoices):
        """Family of a media, deduced from the extension of the uploaded file."""

        IMAGE = "image", "Image"
        PDF = "pdf", "PDF"
        EXCEL = "excel", "Excel"
        WORD = "word", "Word"
        POWERPOINT = "powerpoint", "PowerPoint"
        VIDEO = "video", "Vidéo"

    folder = models.ForeignKey(
        "inspections.InspectionFolder",
        on_delete=models.CASCADE,
        related_name="medias",
        verbose_name="Dossier d'inspection",
    )
    visit = models.ForeignKey(
        "inspections.VisitInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medias",
        verbose_name="Visite",
    )
    recommandation = models.ForeignKey(
        "inspections.Recommandation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medias",
        verbose_name="Recommandation",
    )

    file = models.FileField(upload_to=media_upload_to, verbose_name="Fichier")
    thumbnail = models.ImageField(
        upload_to=thumbnail_upload_to, null=True, blank=True, verbose_name="Miniature"
    )
    original_name = models.CharField(max_length=255, verbose_name="Nom d'origine")
    content_type = models.CharField(max_length=100, verbose_name="Type MIME")
    media_type = models.CharField(
        max_length=20, choices=MediaType.choices, verbose_name="Type"
    )
    size = models.PositiveBigIntegerField(default=0, verbose_name="Taille (octets)")
    # EXIF data of photos: taken_at (ISO), latitude, longitude, camera (keys only when present)
    metadata = models.JSONField(
        blank=True, default=dict, verbose_name="Métadonnées EXIF"
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Légende")
    tags = models.ManyToManyField(
        MediaTag, blank=True, related_name="medias", verbose_name="Tags"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    if TYPE_CHECKING:
        # FK id attributes, declared for Pylance only
        folder_id: int
        visit_id: Optional[int]
        recommandation_id: Optional[int]

    class Meta(TrackingModel.Meta):
        verbose_name = "Média"
        verbose_name_plural = "Médias"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(visit__isnull=True) | Q(recommandation__isnull=True),
                name="media_single_target",
            )
        ]

    def __str__(self) -> str:
        """Return the caption, or the original name."""
        return self.title or self.original_name

    @property
    def display_name(self) -> str:
        """Return the caption if any, otherwise the original name."""
        return self.title or self.original_name

    @property
    def taken_at(self) -> Optional[datetime]:
        """Return the capture date of the photo (local time of the camera), if known."""
        value = self.metadata.get("taken_at")
        try:
            return datetime.fromisoformat(value) if value else None
        except ValueError:
            return None

    @property
    def location_url(self) -> Optional[str]:
        """Return an OpenStreetMap link to the GPS position of the photo, if known."""
        lat, lon = self.metadata.get("latitude"), self.metadata.get("longitude")
        if lat is None or lon is None:
            return None
        return (
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
        )

    @property
    def is_image(self) -> bool:
        """Return True for an image."""
        return self.media_type == self.MediaType.IMAGE

    @property
    def is_video(self) -> bool:
        """Return True for a video."""
        return self.media_type == self.MediaType.VIDEO

    def clean(self) -> None:
        """Check that the target is unique and belongs to the folder of the media.

        Raises:
            ValidationError: If both a visit and a recommendation are set, or the
                target belongs to another folder.
        """
        if self.visit_id and self.recommandation_id:
            raise ValidationError(
                "Un média ne peut être rattaché qu'à une visite ou une recommandation, pas aux deux."
            )
        if self.visit_id and self.visit.folder_id != self.folder_id:
            raise ValidationError("Cette visite n'appartient pas au dossier.")
        if self.recommandation_id and self.recommandation.folder_id != self.folder_id:
            raise ValidationError("Cette recommandation n'appartient pas au dossier.")
