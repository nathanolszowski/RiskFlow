"""Factories and image helpers of the medias app (medias/models.py)."""

from io import BytesIO

import factory
from core.tests.factories import TrackedFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from inspections.tests.factories import InspectionFolderFactory
from PIL import Image

from medias.models import Media, MediaTag


def make_jpeg(size=(100, 80), exif=None, name="photo.jpg"):
    """Build a JPEG upload in memory.

    Args:
        size: ``(width, height)`` in pixels.
        exif: Optional ``{tag id: value}`` mapping written in the EXIF block
            (for example ``{0x0112: 6}`` for the orientation).
        name: File name of the upload.

    Returns:
        A ``SimpleUploadedFile`` of type ``image/jpeg``.
    """
    image = Image.new("RGB", size, (200, 30, 30))
    buffer = BytesIO()
    kwargs = {}
    if exif:
        block = Image.Exif()
        for tag, value in exif.items():
            block[tag] = value
        kwargs["exif"] = block
    image.save(buffer, format="JPEG", **kwargs)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def make_png_rgba(size=(60, 40), name="logo.png"):
    """Build a PNG upload with a transparent background in memory.

    Args:
        size: ``(width, height)`` in pixels.
        name: File name of the upload.

    Returns:
        A ``SimpleUploadedFile`` of type ``image/png``.
    """
    image = Image.new("RGBA", size, (0, 0, 255, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class MediaTagFactory(TrackedFactory):
    """Build a ``MediaTag`` of a user.

    Attributes:
        created_by: A new user.
        name: Unique ``tag<n>`` from a sequence.

    Traits:
        archived: Archived tag (see ``TrackedFactory``).
    """

    class Meta:
        """Bind the factory to the tag model."""

        model = MediaTag

    created_by = factory.SubFactory("accounts.tests.factories.UserFactory")
    name = factory.Sequence(lambda n: f"tag{n}")


class MediaFactory(TrackedFactory):
    """Build a ``Media`` holding a small PDF, attached to a folder only.

    The factory writes the file straight to the storage (``MEDIA_ROOT`` of the test
    settings), it does not go through ``create_media`` and its validation.

    Attributes:
        folder: A new folder by default.
        created_by: The owner of the folder.
        file: A minimal ``doc.pdf``.
        media_type: ``pdf``.

    Traits:
        archived: Archived media (see ``TrackedFactory``).
    """

    class Meta:
        """Bind the factory to the media model."""

        model = Media

    folder = factory.SubFactory(InspectionFolderFactory)
    created_by = factory.SelfAttribute("folder.created_by")
    file = factory.django.FileField(filename="doc.pdf", data=b"%PDF-1.4\n%%EOF\n")
    original_name = "doc.pdf"
    content_type = "application/pdf"
    media_type = Media.MediaType.PDF
    size = 15
