"""Validation of uploaded files: extension, signature and size, per media type.

The MIME type is deduced from the extension, never from the client header, and the
first bytes of the file are checked against the expected format.
"""

import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

OLE = b"\xd0\xcf\x11\xe0"  # legacy Office (.doc, .xls, .ppt)
ZIP = b"PK"  # OOXML Office (.docx, .xlsx, .pptx)

# extension -> (media_type, MIME type)
ALLOWED_EXTENSIONS = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".webp": ("image", "image/webp"),
    ".pdf": ("pdf", "application/pdf"),
    ".xls": ("excel", "application/vnd.ms-excel"),
    ".xlsx": (
        "excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".doc": ("word", "application/msword"),
    ".docx": (
        "word",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".ppt": ("powerpoint", "application/vnd.ms-powerpoint"),
    ".pptx": (
        "powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/quicktime"),
    ".webm": ("video", "video/webm"),
}

# Extensions offered by the file picker
ACCEPT_ATTRIBUTE = ",".join(sorted(ALLOWED_EXTENSIONS))


def _signature_ok(ext: str, head: bytes) -> bool:
    """Check the first bytes of the file against the format of its extension.

    Args:
        ext: Lowercase extension with its dot, among ``ALLOWED_EXTENSIONS``.
        head: First bytes of the file.

    Returns:
        True if the bytes match the format.
    """
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == ".pdf":
        return b"%PDF" in head[:1024]
    if ext in (".xlsx", ".docx", ".pptx"):
        return head.startswith(ZIP)
    if ext in (".xls", ".doc", ".ppt"):
        return head.startswith(OLE)
    if ext in (".mp4", ".mov"):
        return head[4:8] == b"ftyp"
    if ext == ".webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    return False


def max_size_bytes(media_type: str) -> int:
    """Return the maximum size of a received file of this type, in bytes.

    Args:
        media_type: Media type, a key of ``MEDIA_MAX_SIZE_BY_TYPE``.

    Returns:
        The limit in bytes.
    """
    return settings.MEDIA_MAX_SIZE_BY_TYPE[media_type] * 1024 * 1024


def validate_upload(uploaded: UploadedFile) -> tuple[str, str]:
    """Check an uploaded file and return its media type and MIME type.

    Args:
        uploaded: File received from the form.

    Returns:
        A ``(media_type, content_type)`` tuple.

    Raises:
        ValidationError: If the format is not accepted, the content does not match
            the extension, the file is empty or it exceeds the size limit.
    """
    name = uploaded.name or ""
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Format non accepté (images, PDF, Excel, Word, PowerPoint ou vidéo)."
        )
    media_type, content_type = ALLOWED_EXTENSIONS[ext]

    if not uploaded.size:
        raise ValidationError("Le fichier est vide.")
    if uploaded.size > max_size_bytes(media_type):
        raise ValidationError(
            f"Fichier trop volumineux (maximum {settings.MEDIA_MAX_SIZE_BY_TYPE[media_type]} Mo)."
        )

    uploaded.seek(0)
    head = uploaded.read(1024)
    uploaded.seek(0)
    if not _signature_ok(ext, head):
        raise ValidationError("Le contenu ne correspond pas à l'extension du fichier.")

    return media_type, content_type
