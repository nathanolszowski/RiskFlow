"""Image compression, thumbnails and EXIF metadata with Pillow."""

import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from struct import error as struct_error
from typing import Any, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass
class ProcessedImage:
    """Compressed image and its thumbnail, ready to be stored.

    Attributes:
        image: Compressed image (EXIF kept).
        thumbnail: Thumbnail, without EXIF.
        content_type: MIME type of the compressed image.
        metadata: Exploitable EXIF data, see ``extract_metadata``.
    """

    image: ContentFile
    thumbnail: ContentFile
    content_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


# EXIF tags and sub-directories (IFD) used below
EXIF_IFD = 0x8769
GPS_IFD = 0x8825
TAG_DATETIME = 306
TAG_DATETIME_ORIGINAL = 36867
TAG_MAKE = 271
TAG_MODEL = 272


def _dms_to_decimal(dms: Any, ref: Any) -> Optional[float]:
    """Convert a GPS (degrees, minutes, seconds) triple to signed decimal degrees.

    Args:
        dms: Degrees, minutes and seconds, as stored in the EXIF GPS directory.
        ref: Hemisphere reference (``N``, ``S``, ``E`` or ``W``).

    Returns:
        The signed value, or None if ``dms`` is not a valid triple.
    """
    try:
        degrees, minutes, seconds = (float(v) for v in dms)
    except (TypeError, ValueError):
        return None
    value = degrees + minutes / 60 + seconds / 3600
    return -value if str(ref).upper() in ("S", "W") else value


def extract_metadata(exif: Image.Exif) -> dict[str, Any]:
    """Return the exploitable part of the EXIF data of a photo.

    Args:
        exif: EXIF data of the image, after the orientation was applied.

    Returns:
        A dict with the keys present in the image: ``taken_at`` (ISO 8601, local time
        of the camera), ``latitude`` and ``longitude`` (decimal degrees) and ``camera``.
    """
    metadata: dict[str, Any] = {}
    try:
        taken = exif.get_ifd(EXIF_IFD).get(TAG_DATETIME_ORIGINAL) or exif.get(
            TAG_DATETIME
        )
        if taken:
            metadata["taken_at"] = datetime.strptime(
                str(taken).strip(), "%Y:%m:%d %H:%M:%S"
            ).isoformat()
    except (ValueError, KeyError, TypeError, SyntaxError):
        pass
    try:
        gps = exif.get_ifd(GPS_IFD)
        latitude = _dms_to_decimal(gps.get(2), gps.get(1))
        longitude = _dms_to_decimal(gps.get(4), gps.get(3))
        if (
            latitude is not None
            and longitude is not None
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
            # A camera without a fix writes 0/0
            and (latitude or longitude)
        ):
            metadata["latitude"] = round(latitude, 6)
            metadata["longitude"] = round(longitude, 6)
    except (KeyError, TypeError, SyntaxError):
        pass
    camera = " ".join(
        str(v).strip() for v in (exif.get(TAG_MAKE), exif.get(TAG_MODEL)) if v
    )
    if camera:
        metadata["camera"] = camera[:100]
    return metadata


def _has_alpha(img: Image.Image) -> bool:
    """Return True if the image has transparency.

    Args:
        img: Image to inspect.

    Returns:
        Whether it must be kept as PNG to preserve its transparency.
    """
    return img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _encode(
    img: Image.Image, keep_alpha: bool, max_side: int, exif: Optional[bytes] = None
) -> tuple[bytes, str]:
    """Encode a copy of the image fitting in ``max_side``: PNG with transparency, JPEG otherwise.

    ``exif`` is written into the file (the thumbnails get none). A block too large for
    the format is dropped rather than failing the upload.

    Args:
        img: Image to encode, left untouched (a copy is resized).
        keep_alpha: True to encode as PNG, to keep the transparency.
        max_side: Maximum length in pixels of the longest side.
        exif: EXIF block to write into the file, if any.

    Returns:
        The encoded bytes and the extension (``"png"`` or ``"jpg"``).
    """
    img = img.copy()
    img.thumbnail((max_side, max_side))
    for extra in ({"exif": exif}, {}) if exif else ({},):
        buffer = io.BytesIO()
        try:
            if keep_alpha:
                img.convert("RGBA").save(buffer, format="PNG", optimize=True, **extra)
                return buffer.getvalue(), "png"
            img.convert("RGB").save(
                buffer,
                format="JPEG",
                quality=settings.MEDIA_IMAGE_QUALITY,
                optimize=True,
                **extra,
            )
            return buffer.getvalue(), "jpg"
        except (ValueError, OSError, struct_error):
            if not extra:
                raise
    raise AssertionError("unreachable")


def process_image(uploaded: UploadedFile) -> ProcessedImage:
    """Compress an uploaded image and build its thumbnail.

    The orientation stored in the EXIF data is applied, the longest side is limited
    to ``MEDIA_IMAGE_MAX_DIMENSION`` and the image is re-encoded (JPEG, or PNG when it
    has transparency). The EXIF data (capture date, GPS position, camera) is kept in the
    file and its useful part is returned in ``metadata``. The original is kept when it
    is already smaller and untouched.

    Args:
        uploaded: Image received from the form.

    Returns:
        The compressed image, its thumbnail, the MIME type and the EXIF metadata.

    Raises:
        ValidationError: If the file is not a readable image.
    """
    uploaded.seek(0)
    try:
        with Image.open(uploaded) as probe:
            probe.verify()
        uploaded.seek(0)
        with Image.open(uploaded) as opened:
            original_format = opened.format
            original_size = opened.size
            # Pillow only raises above twice its own limit: refuse earlier, before decoding
            if opened.width * opened.height > settings.MEDIA_IMAGE_MAX_PIXELS:
                raise ValidationError(
                    "Image trop grande (définition supérieure à "
                    f"{settings.MEDIA_IMAGE_MAX_PIXELS // 1_000_000} mégapixels)."
                )
            img = ImageOps.exif_transpose(opened)
            img.load()
            # After the transposition the orientation tag is reset, so it is not applied twice
            exif = img.getexif()
            exif_bytes = exif.tobytes() if len(exif) else None
            metadata = extract_metadata(exif)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise ValidationError("Image illisible ou corrompue.")

    keep_alpha = _has_alpha(img)
    data, ext = _encode(img, keep_alpha, settings.MEDIA_IMAGE_MAX_DIMENSION, exif_bytes)
    content_type = "image/png" if ext == "png" else "image/jpeg"

    untouched = (
        img.size == original_size
        and original_format == ("PNG" if keep_alpha else "JPEG")
        and len(data) >= uploaded.size
    )
    stem = os.path.splitext(uploaded.name or "image")[0]
    if untouched:
        uploaded.seek(0)
        image = ContentFile(uploaded.read(), name=f"{stem}.{ext}")
    else:
        image = ContentFile(data, name=f"{stem}.{ext}")

    thumb_data, thumb_ext = _encode(img, False, settings.MEDIA_THUMBNAIL_SIZE)
    thumbnail = ContentFile(thumb_data, name=f"{stem}.{thumb_ext}")
    return ProcessedImage(
        image=image,
        thumbnail=thumbnail,
        content_type=content_type,
        metadata=metadata,
    )
