"""Tests for the medias views (medias/views.py).

Each class has its own temporary ``MEDIA_ROOT``. Archive and delete views of medias
are covered here; the isolation (404 for another user) is in ``test_isolation.py``.
"""

from core.tests.helpers import HtmxClientMixin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from inspections.tests.factories import (
    InspectionFolderFactory,
    RecommandationFactory,
    VisitInstanceFactory,
)

from medias.models import Media
from medias.services.media import create_media
from medias.tests.factories import MediaFactory, MediaTagFactory, make_jpeg
from medias.tests.helpers import TempMediaRootMixin

TAB = "medias/partials/tabs/tab_medias.html"
UPLOAD_MODAL = "medias/partials/media/media_upload_modal.html"
UPDATE_MODAL = "medias/partials/media/media_update_modal.html"
PDF = b"%PDF-1.4\n%%EOF\n"
BODY = (
    b"%PDF-1.4\n" + bytes(range(256)) * 2
)  # 521 bytes, every byte value is distinctive


def pdf(name="rapport.pdf", extra=b""):
    """Build a PDF upload.

    Args:
        name: File name.
        extra: Bytes appended to the minimal PDF.

    Returns:
        A ``SimpleUploadedFile``.
    """
    return SimpleUploadedFile(name, PDF + extra, content_type="application/pdf")


class MediaViewTestCase(TempMediaRootMixin, HtmxClientMixin, TestCase):
    """Base class: a folder of the logged-in ``owner`` with a visit and a recommendation."""

    def setUp(self):
        """Create the folder, its visit and its recommendation."""
        super().setUp()
        self.folder = InspectionFolderFactory(created_by=self.owner)
        kwargs = {"folder": self.folder, "created_by": self.owner}
        self.visit = VisitInstanceFactory(**kwargs)
        self.rec = RecommandationFactory(**kwargs)

    def url(self, name, *args):
        """Reverse a ``medias`` URL.

        Args:
            name: URL name without the namespace.
            *args: URL arguments.

        Returns:
            The URL.
        """
        return reverse(f"medias:{name}", args=args)

    def make_media(self, **kwargs):
        """Create a media of the folder.

        Args:
            **kwargs: Overrides passed to ``MediaFactory``.

        Returns:
            The media.
        """
        kwargs.setdefault("folder", self.folder)
        kwargs.setdefault("created_by", self.owner)
        return MediaFactory(**kwargs)


class MediasTabTests(MediaViewTestCase):
    """``folder_tab_medias`` and its filters."""

    def setUp(self):
        """Create a tagged photo, a PDF on a visit and an archived media."""
        super().setUp()
        self.photo = self.make_media(
            original_name="facade.jpg", media_type="image", title="Façade"
        )
        self.report = self.make_media(original_name="rapport.pdf", visit=self.visit)
        self.old = self.make_media(original_name="ancien.pdf", archived=True)
        self.photo.tags.add(MediaTagFactory(created_by=self.owner, name="Toiture"))
        self.tab_url = self.url("folder_tab_medias", self.folder.pk)

    def listed(self, **params):
        """Return the medias listed by the tab for some filters.

        Args:
            **params: Query string filters.

        Returns:
            A set of medias.
        """
        response = self.htmx_get(self.tab_url, params)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, TAB)
        return set(response.context["medias"])

    def test_default_lists_the_active_medias_with_counters(self):
        """Archived medias are hidden by default and counted apart."""
        response = self.htmx_get(self.tab_url)
        self.assertEqual(set(response.context["medias"]), {self.photo, self.report})
        self.assertEqual(
            (response.context["active_count"], response.context["archived_count"]),
            (2, 1),
        )
        self.assertEqual(response.context["usage"]["level"], "normal")

    def test_filters(self):
        """Status, tag, type, target and search filters apply."""
        self.assertEqual(self.listed(status="archived"), {self.old})
        self.assertEqual(self.listed(tag="Toiture"), {self.photo})
        self.assertEqual(self.listed(tag="toit"), set())
        self.assertEqual(self.listed(media_type="image"), {self.photo})
        self.assertEqual(self.listed(target=f"visit:{self.visit.pk}"), {self.report})
        self.assertEqual(self.listed(target="folder"), {self.photo})
        self.assertEqual(self.listed(q="façade"), {self.photo})
        self.assertEqual(self.listed(q="toiture"), {self.photo})

    def test_tags_offered_are_those_of_the_folder(self):
        """The tag filter only offers tags used in this folder."""
        MediaTagFactory(created_by=self.owner, name="Inutilisé")
        response = self.htmx_get(self.tab_url)
        self.assertEqual([t.name for t in response.context["tags"]], ["Toiture"])

    def test_targets_include_visits_and_recommendations(self):
        """The target filter offers the folder, its visits and its recommendations."""
        response = self.htmx_get(self.tab_url)
        values = {
            value for value, _ in response.context["targets"] if isinstance(value, str)
        }
        self.assertIn("folder", values)
        groups = {
            label: items
            for label, items in response.context["targets"]
            if isinstance(items, list)
        }
        self.assertEqual([v for v, _ in groups["Visites"]], [f"visit:{self.visit.pk}"])
        self.assertEqual(
            [v for v, _ in groups["Recommandations"]], [f"recommandation:{self.rec.pk}"]
        )

    def test_post_is_refused(self):
        """The tab only accepts GET."""
        self.assertEqual(self.client.post(self.tab_url).status_code, 405)


class MediaUploadTests(MediaViewTestCase):
    """``media_upload``: the modal, accepted files and refusals."""

    def setUp(self):
        """Compute the upload URL."""
        super().setUp()
        self.upload_url = self.url("media_upload", self.folder.pk)

    def test_get_renders_the_modal_with_limits_and_quota(self):
        """The modal tells which formats, sizes and how much quota are left."""
        response = self.htmx_get(self.upload_url, {"target": f"visit:{self.visit.pk}"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, UPLOAD_MODAL)
        self.assertEqual(
            response.context["form"].initial["target"], f"visit:{self.visit.pk}"
        )
        self.assertIn(".pdf", response.context["accept"])
        self.assertEqual(response.context["limits_mb"]["pdf"], 25)
        self.assertEqual(response.context["usage"]["used_bytes"], 0)

    def test_valid_upload_returns_the_tab_and_closes_the_modal(self):
        """Several valid files are all stored, with tags, notes and target."""
        response = self.htmx_post(
            self.upload_url,
            {
                "files": [pdf("a.pdf"), make_jpeg(name="b.jpg")],
                "target": f"visit:{self.visit.pk}",
                "notes": "relevé du jour",
                "new_tags": "toiture, feu",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "closeModal")
        self.assertTemplateUsed(response, TAB)
        medias = Media.objects.order_by("original_name")
        self.assertEqual([m.original_name for m in medias], ["a.pdf", "b.jpg"])
        for media in medias:
            self.assertEqual(
                (media.visit, media.notes, media.created_by),
                (self.visit, "relevé du jour", self.owner),
            )
            self.assertEqual(
                sorted(t.name for t in media.tags.all()), ["feu", "toiture"]
            )
        self.assertTrue(medias[1].thumbnail)

    def test_upload_on_a_recommendation(self):
        """A recommendation can be the target."""
        self.htmx_post(
            self.upload_url, {"files": pdf(), "target": f"recommandation:{self.rec.pk}"}
        )
        self.assertEqual(Media.objects.get().recommandation, self.rec)

    def test_refused_file_gives_a_popup_message(self):
        """A refused format answers 422 with its message for the pop-up, nothing stored."""
        response = self.htmx_post(
            self.upload_url,
            {
                "files": SimpleUploadedFile("virus.exe", b"MZ" + b"0" * 10),
                "target": "folder",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.assertEqual(response["HX-Reswap"], "innerHTML")
        self.assertEqual(
            response.context["file_errors"],
            [
                (
                    "virus.exe",
                    "Format non accepté (images, PDF, Excel, Word, PowerPoint ou vidéo).",
                )
            ],
        )
        self.assertIn(
            "« virus.exe » : Format non accepté",
            response.context["file_errors_json"][0],
        )
        self.assertContains(response, "virus.exe", status_code=422)
        self.assertFalse(Media.objects.exists())

    def test_valid_files_are_kept_when_another_is_refused(self):
        """The accepted files of a batch are saved, the tab behind the modal is refreshed."""
        response = self.htmx_post(
            self.upload_url,
            {
                "files": [pdf("bon.pdf"), SimpleUploadedFile("mauvais.exe", b"MZ00")],
                "target": "folder",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual([m.original_name for m in Media.objects.all()], ["bon.pdf"])
        self.assertContains(
            response, 'id="tab-content" hx-swap-oob="innerHTML"', status_code=422
        )
        self.assertContains(response, "bon.pdf", status_code=422)

    def test_content_not_matching_the_extension_is_refused(self):
        """A text file named ``.pdf`` is refused with the signature message."""
        response = self.htmx_post(
            self.upload_url,
            {
                "files": SimpleUploadedFile("faux.pdf", b"plain text"),
                "target": "folder",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("ne correspond pas", response.context["file_errors"][0][1])

    @override_settings(
        MEDIA_MAX_SIZE_BY_TYPE={
            "pdf": 0.001,
            "image": 1,
            "video": 1,
            "excel": 1,
            "word": 1,
            "powerpoint": 1,
        }
    )
    def test_oversized_file_is_refused(self):
        """A file above the limit of its type is refused with its message."""
        response = self.htmx_post(
            self.upload_url, {"files": pdf(extra=b"0" * 3000), "target": "folder"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("trop volumineux", response.context["file_errors"][0][1])

    @override_settings(MEDIA_FOLDER_QUOTA_MB=0.001)
    def test_quota_exceeded_is_refused(self):
        """A file that does not fit in the quota is refused with the quota message."""
        response = self.htmx_post(
            self.upload_url, {"files": pdf(extra=b"0" * 3000), "target": "folder"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Quota", response.context["file_errors"][0][1])
        self.assertFalse(Media.objects.exists())

    def test_no_file_is_422(self):
        """Posting without file re-renders the modal with the form error."""
        response = self.htmx_post(self.upload_url, {"target": "folder"})
        self.assertEqual(response.status_code, 422)
        self.assertIn(
            "Choisissez au moins un fichier", response.context["file_errors_json"][0]
        )

    def test_target_of_another_folder_is_refused(self):
        """A visit of another folder is not an accepted target."""
        foreign = VisitInstanceFactory(
            created_by=self.owner, folder__created_by=self.owner
        )
        response = self.htmx_post(
            self.upload_url, {"files": pdf(), "target": f"visit:{foreign.pk}"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Media.objects.exists())

    def test_too_many_tags_are_refused(self):
        """More than ten tags re-render the modal with an error."""
        tags = ", ".join(f"t{i}" for i in range(11))
        response = self.htmx_post(
            self.upload_url, {"files": pdf(), "target": "folder", "new_tags": tags}
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Media.objects.exists())

    def test_archived_folder_is_409(self):
        """No file can be added to an archived folder."""
        self.folder.archive(self.owner)
        self.assertEqual(self.htmx_get(self.upload_url).status_code, 409)
        self.assertEqual(
            self.htmx_post(
                self.upload_url, {"files": pdf(), "target": "folder"}
            ).status_code,
            409,
        )
        self.assertFalse(Media.objects.exists())


class MediaUpdateTests(MediaViewTestCase):
    """``media_update``: caption, notes, target and tags."""

    def setUp(self):
        """Create a media and a tag of the user."""
        super().setUp()
        self.media = self.make_media()
        self.tag = MediaTagFactory(created_by=self.owner, name="Existant")
        self.make_media().tags.add(self.tag)
        self.update_url = self.url("media_update", self.media.pk)

    def test_get_renders_the_modal_with_the_current_values(self):
        """The modal is pre-filled with the current target and tags."""
        self.media.visit = self.visit
        self.media.save()
        self.media.tags.add(self.tag)
        response = self.htmx_get(self.update_url)
        self.assertTemplateUsed(response, UPDATE_MODAL)
        initial = response.context["form"].initial
        self.assertEqual(initial["target"], f"visit:{self.visit.pk}")
        self.assertEqual(initial["existing_tags"], [self.tag.pk])

    def test_valid_post_updates_and_returns_the_tab(self):
        """Caption, notes, target and tags (existing and new) are saved."""
        response = self.htmx_post(
            self.update_url,
            {
                "title": "Légende",
                "notes": "Remarques",
                "target": f"recommandation:{self.rec.pk}",
                "existing_tags": [self.tag.pk],
                "new_tags": "nouveau",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "closeModal")
        self.assertTemplateUsed(response, TAB)
        self.media.refresh_from_db()
        self.assertEqual((self.media.title, self.media.notes), ("Légende", "Remarques"))
        self.assertEqual(self.media.recommandation, self.rec)
        self.assertEqual(
            sorted(t.name for t in self.media.tags.all()), ["Existant", "nouveau"]
        )
        self.assertEqual(self.media.updated_by, self.owner)

    def test_tag_filter_finds_the_edited_media(self):
        """After tagging, the ``?tag=`` filter of the tab returns the media."""
        self.htmx_post(self.update_url, {"target": "folder", "new_tags": "extincteurs"})
        response = self.htmx_get(
            self.url("folder_tab_medias", self.folder.pk), {"tag": "extincteurs"}
        )
        self.assertEqual(list(response.context["medias"]), [self.media])

    def test_empty_target_detaches_to_the_folder(self):
        """Choosing the folder detaches the media from its visit."""
        self.media.visit = self.visit
        self.media.save()
        self.htmx_post(self.update_url, {"target": "folder"})
        self.media.refresh_from_db()
        self.assertIsNone(self.media.visit)

    def test_invalid_post_is_422_and_retargets_the_modal(self):
        """A target of another folder re-renders the modal and keeps the media unchanged."""
        foreign = VisitInstanceFactory(
            created_by=self.owner, folder__created_by=self.owner
        )
        response = self.htmx_post(
            self.update_url, {"title": "x", "target": f"visit:{foreign.pk}"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.media.refresh_from_db()
        self.assertEqual(self.media.title, "")

    def test_too_many_tags_are_refused(self):
        """Eleven tags are refused with an error on the field."""
        tags = ",".join(f"t{i}" for i in range(11))
        response = self.htmx_post(
            self.update_url, {"target": "folder", "new_tags": tags}
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("new_tags", response.context["form"].errors)

    def test_archived_target_stays_selectable(self):
        """An archived visit that is the current target stays in the choices."""
        self.media.visit = self.visit
        self.media.save()
        self.visit.archive(self.owner)
        response = self.htmx_get(self.update_url)
        labels = [
            label
            for _, items in response.context["form"].fields["target"].choices
            if isinstance(items, list)
            for _, label in items
        ]
        self.assertTrue(any("(archivée)" in label for label in labels))


class MediaFileTests(MediaViewTestCase):
    """``media_file`` and ``media_thumbnail`` on the local storage."""

    def setUp(self):
        """Create a 521-byte PDF media and a real image media with a thumbnail."""
        super().setUp()
        self.media = self.make_media(file__data=BODY, size=len(BODY))
        self.photo = create_media(
            self.folder, self.owner, make_jpeg((800, 600), name="photo.jpg")
        )
        self.file_url = self.url("media_file", self.media.pk)

    def test_full_file(self):
        """The whole file is served inline with its type, size and security headers."""
        response = self.client.get(self.file_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), BODY)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Content-Length"], str(len(BODY)))
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        self.assertIn(
            "rapport", self.make_media(original_name="rapport.pdf").original_name
        )
        self.assertNotIn("Content-Security-Policy", response)

    def test_range_request_gives_206(self):
        """``Range: bytes=0-99`` answers 206 with the first 100 bytes and Content-Range."""
        response = self.client.get(self.file_url, HTTP_RANGE="bytes=0-99")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], f"bytes 0-99/{len(BODY)}")
        self.assertEqual(response["Content-Length"], "100")
        self.assertEqual(b"".join(response.streaming_content), BODY[:100])

    def test_open_ended_and_suffix_ranges(self):
        """``bytes=500-`` gives the end of the file, ``bytes=-21`` its last 21 bytes."""
        response = self.client.get(self.file_url, HTTP_RANGE="bytes=500-")
        self.assertEqual(
            response["Content-Range"], f"bytes 500-{len(BODY) - 1}/{len(BODY)}"
        )
        self.assertEqual(b"".join(response.streaming_content), BODY[500:])
        response = self.client.get(self.file_url, HTTP_RANGE="bytes=-21")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b"".join(response.streaming_content), BODY[-21:])

    def test_range_end_is_capped_to_the_file_size(self):
        """A last byte beyond the end is capped instead of refused."""
        response = self.client.get(self.file_url, HTTP_RANGE="bytes=0-99999")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(
            response["Content-Range"], f"bytes 0-{len(BODY) - 1}/{len(BODY)}"
        )

    def test_invalid_ranges_give_416(self):
        """Unreadable or unsatisfiable ranges answer 416 with the size."""
        for header in (
            "bytes=abc",
            "bytes=-",
            "items=0-5",
            "bytes=9999-10000",
            "bytes=50-10",
        ):
            with self.subTest(header=header):
                response = self.client.get(self.file_url, HTTP_RANGE=header)
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response["Content-Range"], f"bytes */{len(BODY)}")

    def test_download_parameter_forces_the_attachment(self):
        """``?download=1`` serves the file as an attachment."""
        response = self.client.get(self.file_url, {"download": "1"})
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    def test_office_files_are_always_downloaded(self):
        """A Word file is served as an attachment even without ``download``."""
        word = self.make_media(
            original_name="note.docx",
            media_type="word",
            file__filename="note.docx",
            file__data=b"PK\x03\x04" + b"0" * 20,
        )
        response = self.client.get(self.url("media_file", word.pk))
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    def test_non_pdf_files_get_a_sandbox_policy(self):
        """Images are served with ``Content-Security-Policy: sandbox``."""
        response = self.client.get(self.url("media_file", self.photo.pk))
        self.assertEqual(response["Content-Security-Policy"], "sandbox")
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_missing_file_is_404(self):
        """A media whose file disappeared from the storage answers 404."""
        self.media.file.storage.delete(self.media.file.name)
        self.assertEqual(self.client.get(self.file_url).status_code, 404)

    def test_thumbnail(self):
        """The thumbnail of an image is served inline as a JPEG."""
        response = self.client.get(self.url("media_thumbnail", self.photo.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\xff\xd8"))

    def test_media_without_thumbnail_is_404(self):
        """A PDF has no thumbnail."""
        self.assertEqual(
            self.client.get(self.url("media_thumbnail", self.media.pk)).status_code, 404
        )

    def test_post_is_refused(self):
        """Files are read with GET only."""
        self.assertEqual(self.client.post(self.file_url).status_code, 405)


class MediaArchiveDeleteTests(MediaViewTestCase):
    """Archiving and deleting a media re-render the medias tab."""

    def setUp(self):
        """Create a media."""
        super().setUp()
        self.media = self.make_media()

    def test_archive_and_unarchive_return_the_tab(self):
        """Both actions answer with the tab and change the media."""
        response = self.htmx_post(self.url("media_archive", self.media.pk))
        self.assertTemplateUsed(response, TAB)
        self.media.refresh_from_db()
        self.assertFalse(self.media.is_active)
        self.assertEqual(self.media.archived_by, self.owner)
        response = self.htmx_post(self.url("media_unarchive", self.media.pk))
        self.assertTemplateUsed(response, TAB)
        self.media.refresh_from_db()
        self.assertTrue(self.media.is_active)

    def test_archive_without_htmx_redirects_to_the_folder(self):
        """A classic POST redirects to the folder."""
        response = self.client.post(self.url("media_archive", self.media.pk))
        self.assertRedirects(
            response, reverse("inspections:folder_detail", args=[self.folder.pk])
        )

    def test_delete_of_an_active_media_is_blocked(self):
        """The modal blocks and the POST answers 409."""
        response = self.htmx_get(self.url("media_delete", self.media.pk))
        self.assertTrue(response.context["blocking"])
        self.assertEqual(
            self.htmx_post(self.url("media_delete", self.media.pk)).status_code, 409
        )
        self.assertTrue(Media.objects.exists())

    def test_delete_of_an_archived_media_removes_the_file(self):
        """The row and the stored file are removed, the tab is returned."""
        self.media.archive(self.owner)
        storage, name = self.media.file.storage, self.media.file.name
        response = self.htmx_get(self.url("media_delete", self.media.pk))
        self.assertFalse(response.context["blocking"])
        self.assertEqual(response.context["post_target"], "#tab-content")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.htmx_post(self.url("media_delete", self.media.pk))
        self.assertTemplateUsed(response, TAB)
        self.assertFalse(Media.objects.exists())
        self.assertFalse(storage.exists(name))
