"""Isolation tests of the medias URLs: another user gets a 404 on everything.

Same rules as ``inspections/tests/test_isolation.py``: GET and POST on every URL
taking the primary key of a folder or of a media, no change in the database, and
the stored file is never served.
"""

from core.tests.helpers import BOTH, GET, POST, HtmxClientMixin, IsolationMixin, Route
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from inspections.tests.factories import InspectionFolderFactory

from medias.models import Media, MediaTag
from medias.tests.factories import MediaFactory, MediaTagFactory
from medias.tests.helpers import TempMediaRootMixin

FOLDER_ROUTES = [
    Route("medias:folder_tab_medias", "pk", GET),
    Route("medias:media_upload", "folder_id", BOTH),
]
MEDIA_ROUTES = [
    Route("medias:media_update", "pk", BOTH),
    Route("medias:media_file", "pk", GET),
    Route("medias:media_thumbnail", "pk", GET),
    Route("medias:media_archive", "pk", POST),
    Route("medias:media_unarchive", "pk", POST),
    Route("medias:media_delete", "pk", BOTH),
]


class MediaIsolationTests(
    TempMediaRootMixin, IsolationMixin, HtmxClientMixin, TestCase
):
    """Medias of ``owner`` are invisible to ``other``.

    Data: a folder with an active media (a PDF) created by ``owner``; ``other`` is
    logged in.
    """

    def setUp(self):
        """Create the folder and the media of the owner, then log ``other`` in."""
        super().setUp()
        self.folder = InspectionFolderFactory(created_by=self.owner)
        self.media = MediaFactory(folder=self.folder, created_by=self.owner)
        self.client.force_login(self.other)

    def database_state(self):
        """Return a snapshot of the media tables.

        Returns:
            The rows of medias and tags.
        """
        return [list(m.objects.order_by("pk").values()) for m in (Media, MediaTag)]

    def test_folder_media_urls_return_404_to_another_user(self):
        """The medias tab and the upload of a foreign folder answer 404."""
        self.check_routes_404(FOLDER_ROUTES, self.folder)

    def test_media_urls_return_404_to_another_user(self):
        """Every URL of a foreign media answers 404."""
        self.check_routes_404(MEDIA_ROUTES, self.media)

    def test_upload_to_a_foreign_folder_stores_nothing(self):
        """A foreign upload creates neither a row nor a file."""
        url = reverse("medias:media_upload", args=[self.folder.pk])
        upload = SimpleUploadedFile("a.pdf", b"%PDF-1.4\n%%EOF\n")
        response = self.htmx_post(url, {"files": upload, "target": "folder"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Media.objects.count(), 1)

    def test_file_is_served_to_its_owner(self):
        """Control: the owner gets the file."""
        self.client.force_login(self.owner)
        response = self.client.get(reverse("medias:media_file", args=[self.media.pk]))
        self.assertEqual(response.status_code, 200)

    def test_foreign_update_does_not_touch_tags(self):
        """Posting a title or tags on a foreign media changes nothing."""
        url = reverse("medias:media_update", args=[self.media.pk])
        response = self.htmx_post(
            url, {"title": "piraté", "new_tags": "x", "target": "folder"}
        )
        self.assertEqual(response.status_code, 404)
        self.media.refresh_from_db()
        self.assertEqual(self.media.title, "")
        self.assertFalse(MediaTag.objects.exists())

    def test_tag_filter_only_uses_own_tags(self):
        """The medias tab of a user never lists the tags of someone else."""
        MediaTagFactory(created_by=self.owner, name="Secret")
        own = InspectionFolderFactory(created_by=self.other)
        response = self.client.get(reverse("medias:folder_tab_medias", args=[own.pk]))
        self.assertNotContains(response, "Secret")

    def test_medias_of_other_folders_are_not_listed(self):
        """The tab of one's own folder does not list a foreign media."""
        own = InspectionFolderFactory(created_by=self.other)
        response = self.client.get(reverse("medias:folder_tab_medias", args=[own.pk]))
        self.assertEqual(list(response.context["medias"]), [])
        self.assertNotContains(response, "doc.pdf")
