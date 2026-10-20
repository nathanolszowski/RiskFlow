"""Tests for the media services and constraints (medias/services/media.py, models.py, signals.py).

Each class has its own temporary ``MEDIA_ROOT`` (``TempMediaRootMixin``).
"""

import re

from accounts.tests.factories import UserFactory
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import TestCase, override_settings
from inspections.tests.factories import (
    InspectionFolderFactory,
    RecommandationFactory,
    VisitInstanceFactory,
)

from medias.models import Media
from medias.services.media import (
    archive_media,
    create_media,
    delete_media,
    get_filtered_medias,
    get_folder_usage,
    get_media_by_id,
    unarchive_media,
    update_media,
)
from medias.tests.factories import MediaFactory, MediaTagFactory, make_jpeg
from medias.tests.helpers import TempMediaRootMixin

PDF = b"%PDF-1.4\n%%EOF\n"


def pdf(name="doc.pdf", padding=0):
    """Build a PDF upload.

    Args:
        name: File name.
        padding: Number of extra bytes appended after the PDF header.

    Returns:
        A ``SimpleUploadedFile``.
    """
    return SimpleUploadedFile(name, PDF + b"0" * padding)


class CreateMediaTests(TempMediaRootMixin, TestCase):
    """``create_media``: storage, deduced fields, quota and targets."""

    def setUp(self):
        """Create a folder with a visit and a recommendation."""
        self.folder = InspectionFolderFactory()
        self.user = self.folder.created_by
        kwargs = {"folder": self.folder, "created_by": self.user}
        self.visit = VisitInstanceFactory(**kwargs)
        self.recommandation = RecommandationFactory(**kwargs)

    def test_pdf_is_stored_under_a_random_name(self):
        """The file goes to ``folders/<folder id>/<uuid>.pdf``, whatever its name."""
        media = create_media(self.folder, self.user, pdf("Rapport confidentiel.pdf"))
        self.assertRegex(
            media.file.name, rf"^folders/{self.folder.pk}/[0-9a-f]{{32}}\.pdf$"
        )
        self.assertTrue(media.file.storage.exists(media.file.name))
        self.assertEqual(media.original_name, "Rapport confidentiel.pdf")

    def test_deduced_fields(self):
        """Type, MIME type, size and ownership come from the file and the user."""
        media = create_media(
            self.folder, self.user, pdf(padding=10), title="T", notes="N"
        )
        media.refresh_from_db()
        self.assertEqual(media.media_type, "pdf")
        self.assertEqual(media.content_type, "application/pdf")
        self.assertEqual(media.size, len(PDF) + 10)
        self.assertEqual((media.title, media.notes), ("T", "N"))
        self.assertEqual((media.created_by, media.updated_by), (self.user, self.user))
        self.assertIsNone(media.visit)
        self.assertFalse(media.thumbnail)

    def test_image_gets_a_thumbnail_and_metadata(self):
        """An image is compressed, has a thumbnail and its EXIF metadata."""
        photo = make_jpeg((3000, 2000), exif={271: "ACME"})
        media = create_media(self.folder, self.user, photo)
        self.assertEqual(media.media_type, "image")
        self.assertTrue(media.thumbnail)
        self.assertRegex(
            media.thumbnail.name, rf"^folders/{self.folder.pk}/thumbnails/"
        )
        self.assertEqual(media.metadata["camera"], "ACME")
        self.assertEqual(media.size, media.file.size)
        self.assertTrue(media.is_image)

    def test_attached_to_a_visit_and_tagged(self):
        """The target and the tags are saved."""
        media = create_media(
            self.folder,
            self.user,
            pdf(),
            visit=self.visit,
            tags=["Toiture", "toiture", "Feu"],
        )
        self.assertEqual(media.visit, self.visit)
        self.assertEqual(sorted(t.name for t in media.tags.all()), ["Feu", "Toiture"])

    def test_target_of_another_folder_is_refused(self):
        """A visit of another folder cannot be used as a target."""
        foreign = VisitInstanceFactory()
        with self.assertRaises(ValidationError):
            create_media(self.folder, self.user, pdf(), visit=foreign)
        self.assertFalse(Media.objects.exists())

    def test_visit_and_recommandation_together_are_refused(self):
        """A media has one target at most."""
        with self.assertRaises(ValidationError):
            create_media(
                self.folder,
                self.user,
                pdf(),
                visit=self.visit,
                recommandation=self.recommandation,
            )

    def test_refused_file_leaves_no_trace(self):
        """An invalid file raises and creates neither a row nor a file."""
        with self.assertRaises(ValidationError):
            create_media(self.folder, self.user, SimpleUploadedFile("a.exe", b"MZ"))
        self.assertFalse(Media.objects.exists())

    def test_too_many_tags_are_refused_before_storing(self):
        """Invalid tags are detected before any file is written."""
        with self.assertRaises(ValidationError):
            create_media(
                self.folder, self.user, pdf(), tags=[f"t{i}" for i in range(11)]
            )
        self.assertFalse(Media.objects.exists())

    @override_settings(MEDIA_FOLDER_QUOTA_MB=0.001)
    def test_file_above_the_remaining_quota_is_refused(self):
        """A file larger than the space left is refused."""
        with self.assertRaisesMessage(ValidationError, "Quota du dossier dépassé"):
            create_media(self.folder, self.user, pdf(padding=2000))
        self.assertFalse(Media.objects.exists())

    @override_settings(MEDIA_FOLDER_QUOTA_MB=0.001)
    def test_full_folder_refuses_any_file(self):
        """When the quota is reached, no file is accepted at all."""
        MediaFactory(folder=self.folder, created_by=self.user, size=2000)
        with self.assertRaisesMessage(ValidationError, "Quota du dossier atteint"):
            create_media(self.folder, self.user, pdf())

    @override_settings(MEDIA_FOLDER_QUOTA_MB=0.001)
    def test_archived_medias_count_in_the_quota(self):
        """Archived medias still use the quota."""
        MediaFactory(folder=self.folder, created_by=self.user, size=2000, archived=True)
        with self.assertRaises(ValidationError):
            create_media(self.folder, self.user, pdf())


class FolderUsageTests(TestCase):
    """``get_folder_usage``: used space, remaining space and level."""

    def setUp(self):
        """Create a folder."""
        self.folder = InspectionFolderFactory()

    def test_empty_folder(self):
        """A folder without media uses nothing."""
        usage = get_folder_usage(self.folder)
        self.assertEqual(
            (usage["used_bytes"], usage["percent"], usage["level"]), (0, 0, "normal")
        )
        self.assertEqual(usage["quota_bytes"], 500 * 1024 * 1024)

    @override_settings(MEDIA_FOLDER_QUOTA_MB=1)
    def test_sizes_are_added_archived_included(self):
        """Archived medias count, medias of other folders do not."""
        MediaFactory(folder=self.folder, created_by=self.folder.created_by, size=1000)
        MediaFactory(
            folder=self.folder,
            created_by=self.folder.created_by,
            size=500,
            archived=True,
        )
        MediaFactory(size=7000)
        usage = get_folder_usage(self.folder)
        self.assertEqual(usage["used_bytes"], 1500)
        self.assertEqual(usage["remaining_bytes"], 1024 * 1024 - 1500)

    @override_settings(MEDIA_FOLDER_QUOTA_MB=1)
    def test_levels(self):
        """The level is normal under 80 %, warning from 80 %, full from 100 %."""
        quota = 1024 * 1024
        for size, level, percent in (
            (-(-quota * 79 // 100), "normal", 79),
            (-(-quota * 80 // 100), "warning", 80),
            (quota, "full", 100),
            (quota * 2, "full", 100),
        ):
            with self.subTest(level=level, size=size):
                Media.objects.filter(folder=self.folder).delete()
                MediaFactory(
                    folder=self.folder, created_by=self.folder.created_by, size=size
                )
                usage = get_folder_usage(self.folder)
                self.assertEqual((usage["level"], usage["percent"]), (level, percent))
        self.assertEqual(usage["remaining_bytes"], 0)


class MediaQueriesTests(TempMediaRootMixin, TestCase):
    """``get_media_by_id`` and ``get_filtered_medias``."""

    def setUp(self):
        """Create a folder holding a photo, a report on a visit and an archived media."""
        self.folder = InspectionFolderFactory()
        self.user = self.folder.created_by
        kwargs = {"folder": self.folder, "created_by": self.user}
        self.visit = VisitInstanceFactory(**kwargs)
        self.photo = MediaFactory(
            title="Façade nord", original_name="img1.jpg", media_type="image", **kwargs
        )
        self.report = MediaFactory(
            original_name="rapport.pdf", notes="incendie", visit=self.visit, **kwargs
        )
        self.old = MediaFactory(original_name="old.pdf", archived=True, **kwargs)
        tag = MediaTagFactory(created_by=self.user, name="Toiture")
        self.photo.tags.add(tag)

    def media(self, **filters):
        """Return the set of medias of the folder for some filters.

        Args:
            **filters: Keyword filters of ``get_filtered_medias``.

        Returns:
            A set of medias.
        """
        return set(get_filtered_medias(self.folder, self.user, **filters))

    def test_default_lists_the_active_medias(self):
        """Archived medias are hidden by default."""
        self.assertEqual(self.media(), {self.photo, self.report})
        self.assertEqual(self.media(status="archived"), {self.old})

    def test_search_covers_title_name_notes_and_tags(self):
        """The search matches the caption, the original name, the notes and the tags."""
        self.assertEqual(self.media(q="façade"), {self.photo})
        self.assertEqual(self.media(q="rapport"), {self.report})
        self.assertEqual(self.media(q="INCENDIE"), {self.report})
        self.assertEqual(self.media(q="toit"), {self.photo})
        self.assertEqual(self.media(q="introuvable"), set())

    def test_search_does_not_duplicate_medias(self):
        """A media with several matching tags appears once."""
        self.photo.tags.add(MediaTagFactory(created_by=self.user, name="Toiture bis"))
        self.assertEqual(len(get_filtered_medias(self.folder, self.user, q="toit")), 1)

    def test_tag_filter_is_exact_and_case_insensitive(self):
        """``tag=`` keeps the medias with this exact tag."""
        self.assertEqual(self.media(tag="toiture"), {self.photo})
        self.assertEqual(self.media(tag="toit"), set())

    def test_type_and_target_filters(self):
        """The type and the target filters apply, unknown types are ignored."""
        self.assertEqual(self.media(media_type="image"), {self.photo})
        self.assertEqual(self.media(media_type="nonsense"), {self.photo, self.report})
        self.assertEqual(self.media(target="folder"), {self.photo})
        self.assertEqual(self.media(target=f"visit:{self.visit.pk}"), {self.report})
        self.assertEqual(self.media(target="visit:abc"), {self.photo, self.report})

    def test_other_users_see_nothing(self):
        """The filter is bound to the owner of the folder."""
        found = get_filtered_medias(self.folder, UserFactory())
        self.assertFalse(found.exists())

    def test_get_media_by_id(self):
        """The owner gets the media, others a 404."""
        self.assertEqual(get_media_by_id(self.photo.pk, self.user), self.photo)
        with self.assertRaises(Http404):
            get_media_by_id(self.photo.pk, UserFactory())
        with self.assertRaises(Http404):
            get_media_by_id(0, self.user)


class UpdateAndLifecycleTests(TempMediaRootMixin, TestCase):
    """``update_media``, archiving and deletion."""

    def setUp(self):
        """Create a media with a visit available as target."""
        self.media = MediaFactory()
        self.user = self.media.created_by
        self.visit = VisitInstanceFactory(
            folder=self.media.folder, created_by=self.user
        )

    def test_update_fields_and_tags(self):
        """The caption, the target and the tags are updated together."""
        update_media(
            self.media, self.user, title="Nouveau", visit=self.visit, tags=["a", "b"]
        )
        self.media.refresh_from_db()
        self.assertEqual(self.media.title, "Nouveau")
        self.assertEqual(self.media.visit, self.visit)
        self.assertEqual(sorted(t.name for t in self.media.tags.all()), ["a", "b"])

    def test_tags_none_leaves_the_tags_unchanged(self):
        """Without ``tags`` the existing tags stay."""
        update_media(self.media, self.user, tags=["a"])
        update_media(self.media, self.user, title="x")
        self.assertEqual([t.name for t in self.media.tags.all()], ["a"])

    def test_update_with_a_foreign_target_is_refused(self):
        """A visit of another folder is refused."""
        with self.assertRaises(ValidationError):
            update_media(self.media, self.user, visit=VisitInstanceFactory())

    def test_archive_and_unarchive(self):
        """Archiving and restoring a media sets and clears the tracking fields."""
        archive_media(self.media, self.user)
        self.media.refresh_from_db()
        self.assertFalse(self.media.is_active)
        self.assertEqual(self.media.archived_by, self.user)
        unarchive_media(self.media, self.user)
        self.media.refresh_from_db()
        self.assertTrue(self.media.is_active)
        self.assertIsNone(self.media.archived_at)

    def test_delete_refuses_an_active_media(self):
        """An active media cannot be deleted."""
        with self.assertRaises(ValueError):
            delete_media(self.media)
        self.assertTrue(Media.objects.filter(pk=self.media.pk).exists())

    def test_delete_removes_the_file_and_the_thumbnail(self):
        """After deletion the file and the thumbnail are gone from the storage."""
        media = create_media(
            self.media.folder, self.user, make_jpeg((500, 400), name="p.jpg")
        )
        storage = media.file.storage
        names = [media.file.name, media.thumbnail.name]
        self.assertTrue(all(storage.exists(n) for n in names))
        archive_media(media, self.user)
        with self.captureOnCommitCallbacks(execute=True):
            delete_media(media)
        self.assertFalse(Media.objects.filter(pk=media.pk).exists())
        self.assertFalse(any(storage.exists(n) for n in names))


class MediaConstraintsTests(TestCase):
    """``Media.clean()`` and the database ``CheckConstraint``."""

    def setUp(self):
        """Create a media with a visit and a recommendation of the same folder."""
        self.media = MediaFactory()
        kwargs = {"folder": self.media.folder, "created_by": self.media.created_by}
        self.visit = VisitInstanceFactory(**kwargs)
        self.recommandation = RecommandationFactory(**kwargs)

    def test_visit_and_recommandation_together_are_refused(self):
        """``clean()`` refuses two targets."""
        self.media.visit = self.visit
        self.media.recommandation = self.recommandation
        with self.assertRaisesMessage(ValidationError, "pas aux deux"):
            self.media.clean()
        with self.assertRaises(ValidationError):
            self.media.save()

    def test_visit_of_another_folder_is_refused(self):
        """``clean()`` refuses a visit of another folder."""
        self.media.visit = VisitInstanceFactory()
        with self.assertRaisesMessage(ValidationError, "visite n'appartient pas"):
            self.media.clean()

    def test_recommandation_of_another_folder_is_refused(self):
        """``clean()`` refuses a recommendation of another folder."""
        self.media.recommandation = RecommandationFactory()
        with self.assertRaisesMessage(
            ValidationError, "recommandation n'appartient pas"
        ):
            self.media.clean()

    def test_save_with_other_update_fields_skips_clean(self):
        """A partial save that does not touch the target does not call ``clean()``."""
        self.media.visit = VisitInstanceFactory()
        self.media.title = "partial"
        self.media.save(update_fields=["title"])
        self.media.refresh_from_db()
        self.assertEqual(self.media.title, "partial")
        self.assertIsNone(self.media.visit)

    def test_check_constraint_blocks_two_targets_even_without_clean(self):
        """The database refuses two targets when ``clean()`` is bypassed."""
        self.media.visit = self.visit
        self.media.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Media.objects.filter(pk=self.media.pk).update(
                recommandation=self.recommandation
            )

    def test_properties(self):
        """Display name, capture date and location link are derived from the fields."""
        self.assertEqual(self.media.display_name, "doc.pdf")
        self.media.title = "Légende"
        self.assertEqual(self.media.display_name, "Légende")
        self.assertIsNone(self.media.taken_at)
        self.assertIsNone(self.media.location_url)
        self.media.metadata = {
            "taken_at": "2024-05-06T07:08:09",
            "latitude": 48.5,
            "longitude": 2.25,
        }
        self.assertEqual(self.media.taken_at.year, 2024)
        self.assertRegex(self.media.location_url, r"mlat=48\.5&mlon=2\.25")
        self.media.metadata = {"taken_at": "garbage"}
        self.assertIsNone(self.media.taken_at)


class StoredFileSignalTests(TempMediaRootMixin, TestCase):
    """The ``post_delete`` signal removes the files of a deleted media."""

    def test_file_is_removed_after_the_commit(self):
        """The file disappears once the deletion is committed, not before."""
        media = MediaFactory()
        storage, name = media.file.storage, media.file.name
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            media.delete()
        self.assertTrue(storage.exists(name))
        for callback in callbacks:
            callback()
        self.assertFalse(storage.exists(name))

    def test_media_without_thumbnail_does_not_fail(self):
        """A media with no thumbnail is deleted without error."""
        media = MediaFactory()
        with self.captureOnCommitCallbacks(execute=True):
            media.delete()
        self.assertTrue(re.match(r"folders/", media.file.name))
