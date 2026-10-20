"""Tests for the image processing (medias/services/images.py).

Images are generated in memory with Pillow. The size limits are lowered with
``override_settings`` instead of building huge images.
"""

import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from medias.services.images import (
    _has_alpha,
    extract_metadata,
    process_image,
)
from medias.tests.factories import make_jpeg, make_png_rgba

ORIENTATION = 0x0112
MAKE, MODEL = 271, 272


def open_result(content_file):
    """Open the image held by a processed ``ContentFile``.

    Args:
        content_file: ``ProcessedImage.image`` or ``.thumbnail``.

    Returns:
        The Pillow image.
    """
    return Image.open(io.BytesIO(content_file.read()))


def exif_with_gps(lat_ref="N", lon_ref="E"):
    """Build an EXIF block with a capture date, a camera and a GPS position.

    Args:
        lat_ref: Latitude reference, ``N`` or ``S``.
        lon_ref: Longitude reference, ``E`` or ``W``.

    Returns:
        The EXIF block (48°51'24" and 2°21'7").
    """
    exif = Image.Exif()
    exif[MAKE] = "ACME"
    exif[MODEL] = "Cam 1"
    exif.get_ifd(0x8769)[36867] = "2024:05:06 07:08:09"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = lat_ref, (48.0, 51.0, 24.0)
    gps[3], gps[4] = lon_ref, (2.0, 21.0, 7.0)
    return exif


def jpeg_with_exif(exif, size=(80, 60)):
    """Build a JPEG upload carrying the given EXIF block.

    Args:
        exif: EXIF block to write.
        size: ``(width, height)`` in pixels.

    Returns:
        A ``SimpleUploadedFile``.
    """
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="JPEG", exif=exif)
    return SimpleUploadedFile("geo.jpg", buffer.getvalue(), content_type="image/jpeg")


class ProcessImageTests(SimpleTestCase):
    """Compression, orientation, format and thumbnail."""

    def test_exif_orientation_is_applied(self):
        """An image with orientation 6 comes out rotated: width and height swap."""
        result = process_image(make_jpeg((100, 50), exif={ORIENTATION: 6}))
        self.assertEqual(open_result(result.image).size, (50, 100))

    def test_large_image_is_reduced_to_the_maximum_dimension(self):
        """A 4000 px image is reduced to 2000 px on its longest side."""
        result = process_image(make_jpeg((4000, 1000)))
        self.assertEqual(open_result(result.image).size, (2000, 500))

    def test_small_image_is_not_enlarged(self):
        """An image under the limit keeps its size."""
        result = process_image(make_jpeg((300, 200)))
        self.assertEqual(open_result(result.image).size, (300, 200))

    def test_output_is_a_jpeg(self):
        """An opaque image is stored as JPEG."""
        result = process_image(make_jpeg((100, 100)))
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertEqual(open_result(result.image).format, "JPEG")
        self.assertTrue(result.image.name.endswith(".jpg"))

    def test_png_with_alpha_stays_a_png(self):
        """A transparent PNG keeps its transparency, so it stays a PNG."""
        result = process_image(make_png_rgba())
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(open_result(result.image).format, "PNG")
        self.assertTrue(result.image.name.endswith(".png"))

    def test_thumbnail_is_at_most_400_pixels_and_without_exif(self):
        """The thumbnail fits in 400 px, is a JPEG and carries no EXIF."""
        result = process_image(jpeg_with_exif(exif_with_gps(), size=(1000, 800)))
        thumbnail = open_result(result.thumbnail)
        self.assertEqual(max(thumbnail.size), 400)
        self.assertEqual(thumbnail.format, "JPEG")
        self.assertEqual(len(thumbnail.getexif()), 0)

    @override_settings(MEDIA_IMAGE_MAX_PIXELS=1000)
    def test_image_above_the_pixel_limit_is_refused(self):
        """An image with too many pixels is refused before being decoded."""
        with self.assertRaisesMessage(ValidationError, "Image trop grande"):
            process_image(make_jpeg((100, 100)))

    @override_settings(MEDIA_IMAGE_MAX_PIXELS=10_000)
    def test_image_at_the_pixel_limit_is_accepted(self):
        """The limit itself is accepted."""
        process_image(make_jpeg((100, 100)))

    def test_corrupted_image_is_refused(self):
        """A file that is not an image gives a readable error."""
        fake = SimpleUploadedFile("a.jpg", b"definitely not an image")
        with self.assertRaisesMessage(ValidationError, "illisible"):
            process_image(fake)

    def test_exif_is_kept_in_the_output_file(self):
        """The camera and the GPS position are still in the stored file."""
        result = process_image(jpeg_with_exif(exif_with_gps()))
        exif = open_result(result.image).getexif()
        self.assertEqual(exif.get(MAKE), "ACME")
        self.assertIn(1, exif.get_ifd(0x8825))

    def test_metadata_is_extracted(self):
        """The result carries the metadata read from the EXIF block."""
        result = process_image(jpeg_with_exif(exif_with_gps()))
        self.assertEqual(result.metadata["camera"], "ACME Cam 1")
        self.assertEqual(result.metadata["taken_at"], "2024-05-06T07:08:09")

    def test_photo_without_exif_has_no_metadata(self):
        """A photo without EXIF gives an empty metadata dict."""
        self.assertEqual(process_image(make_jpeg()).metadata, {})


class ExtractMetadataTests(SimpleTestCase):
    """``extract_metadata`` on hand-made EXIF blocks."""

    def test_gps_in_decimal_degrees(self):
        """Degrees, minutes and seconds become decimal degrees."""
        metadata = extract_metadata(exif_with_gps("N", "E"))
        self.assertAlmostEqual(metadata["latitude"], 48.856667, places=5)
        self.assertAlmostEqual(metadata["longitude"], 2.351944, places=5)

    def test_south_and_west_are_negative(self):
        """The references S and W give negative coordinates."""
        metadata = extract_metadata(exif_with_gps("S", "W"))
        self.assertLess(metadata["latitude"], 0)
        self.assertLess(metadata["longitude"], 0)

    def test_taken_at_and_camera(self):
        """The capture date is ISO 8601 and the camera joins make and model."""
        metadata = extract_metadata(exif_with_gps())
        self.assertEqual(metadata["taken_at"], "2024-05-06T07:08:09")
        self.assertEqual(metadata["camera"], "ACME Cam 1")

    def test_zero_position_is_ignored(self):
        """A 0/0 position (no GPS fix) is not reported."""
        exif = Image.Exif()
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2], gps[3], gps[4] = "N", (0.0, 0.0, 0.0), "E", (0.0, 0.0, 0.0)
        self.assertNotIn("latitude", extract_metadata(exif))

    def test_out_of_range_position_is_ignored(self):
        """A latitude above 90° is not reported."""
        exif = Image.Exif()
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2], gps[3], gps[4] = "N", (95.0, 0.0, 0.0), "E", (2.0, 0.0, 0.0)
        self.assertNotIn("latitude", extract_metadata(exif))

    def test_invalid_date_is_ignored(self):
        """A capture date that cannot be parsed is dropped without error."""
        exif = Image.Exif()
        exif.get_ifd(0x8769)[36867] = "not a date"
        self.assertNotIn("taken_at", extract_metadata(exif))

    def test_empty_exif(self):
        """No EXIF gives no metadata."""
        self.assertEqual(extract_metadata(Image.Exif()), {})


class HasAlphaTests(SimpleTestCase):
    """``_has_alpha`` decides between PNG and JPEG."""

    def test_modes(self):
        """RGBA and LA have alpha, RGB does not, a palette with transparency does."""
        self.assertTrue(_has_alpha(Image.new("RGBA", (1, 1))))
        self.assertTrue(_has_alpha(Image.new("LA", (1, 1))))
        self.assertFalse(_has_alpha(Image.new("RGB", (1, 1))))
        palette = Image.new("P", (1, 1))
        self.assertFalse(_has_alpha(palette))
        palette.info["transparency"] = 0
        self.assertTrue(_has_alpha(palette))
