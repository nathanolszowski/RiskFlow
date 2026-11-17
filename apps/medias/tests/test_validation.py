"""Tests for the upload validation (medias/services/validation.py)."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from medias.services.validation import max_size_bytes, validate_upload
from medias.tests.factories import make_jpeg, make_png_rgba

PDF = b"%PDF-1.4\n%%EOF\n"
ZIP = b"PK\x03\x04" + b"\x00" * 20
OLE = b"\xd0\xcf\x11\xe0" + b"\x00" * 20
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20


def upload(name, content):
    """Build an upload.

    Args:
        name: File name, its extension decides the expected format.
        content: Bytes of the file.

    Returns:
        A ``SimpleUploadedFile``.
    """
    return SimpleUploadedFile(name, content)


class ExtensionTests(SimpleTestCase):
    """Accepted and refused extensions, and the values returned."""

    def test_accepted_extension_returns_type_and_mime(self):
        """The media type and MIME type come from the extension."""
        self.assertEqual(
            validate_upload(upload("rapport.pdf", PDF)), ("pdf", "application/pdf")
        )
        self.assertEqual(validate_upload(make_jpeg()), ("image", "image/jpeg"))
        self.assertEqual(validate_upload(make_png_rgba()), ("image", "image/png"))

    def test_extension_is_case_insensitive(self):
        """``.PDF`` is accepted like ``.pdf``."""
        self.assertEqual(validate_upload(upload("RAPPORT.PDF", PDF))[0], "pdf")

    def test_refused_extensions(self):
        """Executables, scripts, unknown extensions and names without one are refused."""
        for name in (
            "virus.exe",
            "page.html",
            "archive.zip",
            "noextension",
            "x.pdf.exe",
        ):
            with self.subTest(name=name):
                with self.assertRaisesMessage(ValidationError, "Format non accepté"):
                    validate_upload(upload(name, PDF))

    def test_empty_file_is_refused(self):
        """A file without content is refused."""
        with self.assertRaisesMessage(ValidationError, "vide"):
            validate_upload(upload("a.pdf", b""))


class SignatureTests(SimpleTestCase):
    """The first bytes must match the format announced by the extension."""

    def test_pdf_containing_a_png_is_refused(self):
        """A ``.pdf`` whose content is a PNG is refused."""
        png = make_png_rgba().read()
        with self.assertRaisesMessage(ValidationError, "ne correspond pas"):
            validate_upload(upload("fake.pdf", png))

    def test_jpg_containing_text_is_refused(self):
        """A ``.jpg`` that is plain text is refused."""
        with self.assertRaisesMessage(ValidationError, "ne correspond pas"):
            validate_upload(upload("fake.jpg", b"just some text, not an image"))

    def test_png_with_a_jpeg_extension_is_refused(self):
        """The signature of another image format does not pass."""
        with self.assertRaises(ValidationError):
            validate_upload(upload("a.jpg", make_png_rgba().read()))

    def test_valid_signatures_are_accepted(self):
        """Each supported family accepts its own signature."""
        cases = {
            "a.webp": ("image", WEBP),
            "a.docx": ("word", ZIP),
            "a.xlsx": ("excel", ZIP),
            "a.pptx": ("powerpoint", ZIP),
            "a.doc": ("word", OLE),
            "a.xls": ("excel", OLE),
            "a.ppt": ("powerpoint", OLE),
            "a.mp4": ("video", MP4),
            "a.mov": ("video", MP4),
            "a.webm": ("video", WEBM),
        }
        for name, (media_type, content) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(validate_upload(upload(name, content))[0], media_type)

    def test_office_signatures_are_not_interchangeable(self):
        """A modern Office extension needs a zip, a legacy one needs an OLE file."""
        with self.assertRaises(ValidationError):
            validate_upload(upload("a.docx", OLE))
        with self.assertRaises(ValidationError):
            validate_upload(upload("a.doc", ZIP))

    def test_video_without_ftyp_box_is_refused(self):
        """An ``.mp4`` that has no ``ftyp`` box is refused."""
        with self.assertRaises(ValidationError):
            validate_upload(upload("a.mp4", b"\x00" * 32))

    def test_pdf_signature_may_follow_a_short_preamble(self):
        """``%PDF`` is searched in the first kilobyte, not only at offset 0."""
        validate_upload(upload("a.pdf", b"\n" * 100 + PDF))
        with self.assertRaises(ValidationError):
            validate_upload(upload("a.pdf", b"\n" * 2000 + PDF))

    def test_file_position_is_rewound(self):
        """The file can be read from the start after the validation."""
        uploaded = upload("a.pdf", PDF)
        validate_upload(uploaded)
        self.assertEqual(uploaded.read(), PDF)


class SizeTests(SimpleTestCase):
    """Size limits per media type."""

    def test_max_size_bytes_converts_megabytes(self):
        """The limit in settings is in MB, the function returns bytes."""
        with override_settings(MEDIA_MAX_SIZE_BY_TYPE={"pdf": 2}):
            self.assertEqual(max_size_bytes("pdf"), 2 * 1024 * 1024)

    def test_file_above_the_limit_is_refused(self):
        """A file larger than the limit of its type is refused, at the limit it passes."""
        with override_settings(MEDIA_MAX_SIZE_BY_TYPE={"pdf": 0.001, "video": 1}):
            limit = int(max_size_bytes("pdf"))
            validate_upload(upload("a.pdf", PDF + b"0" * (limit - len(PDF))))
            with self.assertRaisesMessage(ValidationError, "trop volumineux"):
                validate_upload(upload("a.pdf", PDF + b"0" * (limit - len(PDF) + 1)))

    def test_limits_are_per_type(self):
        """A size accepted for a video can be refused for a PDF."""
        with override_settings(MEDIA_MAX_SIZE_BY_TYPE={"pdf": 0.001, "video": 1}):
            content = b"0" * 5000
            with self.assertRaises(ValidationError):
                validate_upload(upload("a.pdf", PDF + content))
            validate_upload(upload("a.mp4", MP4 + content))
