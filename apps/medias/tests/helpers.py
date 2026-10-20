"""Helpers shared by the medias tests."""

import shutil
import tempfile

from django.test import override_settings


class TempMediaRootMixin:
    """Give each test class its own temporary ``MEDIA_ROOT``, removed at the end.

    The test settings already point ``MEDIA_ROOT`` to a temporary folder, but a
    folder per class keeps the classes from seeing each other's files (quota,
    storage assertions). Put the mixin before ``TestCase`` in the bases.

    Attributes:
        media_root: Path of the temporary folder of the class.
    """

    @classmethod
    def setUpClass(cls):
        """Create the temporary folder and make it the media root."""
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix="riskflow-test-class-")
        cls._media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        """Restore the settings and delete the temporary folder."""
        cls._media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()
