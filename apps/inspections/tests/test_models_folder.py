"""Tests for the folder lifecycle (inspections/models.py) and its services.

Covers archiving cascades, the reference, ``clean()``, the computed properties, the
deletion cascades (files included) and ``inspections/services/inspectionfolder.py``.
Stored files live in the temporary ``MEDIA_ROOT`` of the test settings.
"""

from datetime import timedelta
from unittest import mock

from accounts.tests.factories import UserFactory
from crm.tests.factories import CompanyFactory, ContactFactory
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone
from medias.models import Media
from medias.tests.factories import MediaFactory

from inspections.models import InspectionFolder, Recommandation, VisitInstance
from inspections.services.inspectionfolder import (
    get_company_folders,
    get_filtered_folders,
    get_inspection_folder_by_id,
    get_inspection_folders_by_user,
)
from inspections.services.recommandation import get_recommandation_by_id
from inspections.tests.factories import (
    InspectionFolderFactory,
    RecommandationFactory,
    VisitInstanceFactory,
)


class FolderTreeMixin:
    """Create a folder holding a visit, a recommendation and a media (with one file each).

    Attributes:
        folder: The folder.
        user: Its owner.
        visit: An active visit of the folder.
        recommandation: An active recommendation of the folder.
        media: An active media of the folder.
    """

    def setUp(self):
        """Create the tree: one child of each kind."""
        super().setUp()
        self.folder = InspectionFolderFactory()
        self.user = self.folder.created_by
        kwargs = {"folder": self.folder, "created_by": self.user}
        self.visit = VisitInstanceFactory(**kwargs)
        self.recommandation = RecommandationFactory(**kwargs)
        self.media = MediaFactory(**kwargs)


class FolderArchiveCascadeTests(FolderTreeMixin, TestCase):
    """``cascade_archive`` and ``cascade_unarchive`` of ``InspectionFolder``."""

    def test_archive_gives_children_the_same_date(self):
        """Visits, recommendations and medias get the archive date of the folder."""
        other = UserFactory()
        self.folder.archive(other)
        for obj in (self.visit, self.recommandation, self.media):
            with self.subTest(model=type(obj).__name__):
                obj.refresh_from_db()
                self.assertFalse(obj.is_active)
                self.assertEqual(obj.archived_at, self.folder.archived_at)
                self.assertEqual(obj.archived_by, other)
                self.assertEqual(obj.updated_by, other)

    def test_archive_skips_children_already_archived(self):
        """A child archived earlier keeps its own date."""
        old = VisitInstanceFactory(
            folder=self.folder, created_by=self.user, archived=True
        )
        previous = old.archived_at
        self.folder.archive(self.user)
        old.refresh_from_db()
        self.assertEqual(old.archived_at, previous)

    def test_unarchive_restores_the_children_archived_with_it(self):
        """Children archived together with the folder come back."""
        self.folder.archive(self.user)
        self.folder.unarchive(self.user)
        for obj in (self.visit, self.recommandation, self.media):
            with self.subTest(model=type(obj).__name__):
                obj.refresh_from_db()
                self.assertTrue(obj.is_active)
                self.assertIsNone(obj.archived_at)
                self.assertIsNone(obj.archived_by)

    def test_unarchive_keeps_children_archived_before(self):
        """A visit archived the day before the folder stays archived."""
        yesterday = VisitInstanceFactory(
            folder=self.folder, created_by=self.user, archived=True
        )
        VisitInstance.objects.filter(pk=yesterday.pk).update(
            archived_at=timezone.now() - timedelta(days=1)
        )
        self.folder.archive(self.user)
        self.folder.unarchive(self.user)
        yesterday.refresh_from_db()
        self.visit.refresh_from_db()
        self.assertFalse(yesterday.is_active)
        self.assertTrue(self.visit.is_active)

    def test_cascade_unarchive_without_date_does_nothing(self):
        """Without the previous archive date nothing is restored."""
        self.folder.archive(self.user)
        self.folder.cascade_unarchive(archived_at=None, user=self.user)
        self.visit.refresh_from_db()
        self.assertFalse(self.visit.is_active)


class FolderReferenceAndCleanTests(TestCase):
    """``reference`` generation and ``clean()`` of the folder."""

    def test_reference_format(self):
        """The reference is ``DOS-<year>-`` followed by six upper-case hex digits."""
        folder = InspectionFolderFactory()
        self.assertRegex(folder.reference, r"^DOS-\d{4}-[0-9A-F]{6}$")
        self.assertIn(str(timezone.now().year), folder.reference)

    def test_references_are_unique(self):
        """Several folders get distinct references."""
        folders = InspectionFolderFactory.create_batch(5)
        self.assertEqual(len({f.reference for f in folders}), 5)

    def test_reference_is_stable_on_resave(self):
        """Saving again never changes the reference."""
        folder = InspectionFolderFactory()
        reference = folder.reference
        folder.notes = "changed"
        folder.save()
        folder.refresh_from_db()
        self.assertEqual(folder.reference, reference)

    def test_generate_unique_reference_skips_a_taken_value(self):
        """A generated value already used by a folder is skipped for the next one."""
        taken = InspectionFolderFactory()
        values = iter([taken.reference[-6:].lower() + "0" * 26, "123abc" + "0" * 26])
        with mock.patch(
            "inspections.models.uuid.uuid4",
            side_effect=lambda: mock.Mock(hex=next(values)),
        ):
            reference = InspectionFolder().generate_unique_reference()
        self.assertEqual(reference, f"DOS-{timezone.now().year}-123ABC")

    def test_contact_of_another_company_is_refused(self):
        """``clean()`` and ``save()`` refuse a contact of another client."""
        folder = InspectionFolderFactory()
        folder.contact = ContactFactory()
        with self.assertRaises(ValidationError) as ctx:
            folder.clean()
        self.assertIn("contact", ctx.exception.message_dict)
        with self.assertRaises(ValidationError):
            folder.save()

    def test_changing_company_checks_the_contact_again(self):
        """Moving the folder to another client while keeping the contact is refused."""
        folder = InspectionFolderFactory()
        folder.company = CompanyFactory()
        with self.assertRaises(ValidationError):
            folder.save()

    def test_save_with_archive_fields_skips_clean(self):
        """``save(update_fields=[...archive...])`` does not call ``clean()``."""
        folder = InspectionFolderFactory()
        folder.contact = ContactFactory()  # invalid on purpose, not saved
        folder.is_active = False
        folder.save(update_fields=["is_active"])
        folder.refresh_from_db()
        self.assertFalse(folder.is_active)

    def test_save_with_contact_in_update_fields_runs_clean(self):
        """A partial save that touches the contact is still checked."""
        folder = InspectionFolderFactory()
        folder.contact = ContactFactory()
        with self.assertRaises(ValidationError):
            folder.save(update_fields=["contact"])

    def test_folder_without_contact_is_valid(self):
        """The contact is optional."""
        folder = InspectionFolderFactory(contact=None)
        folder.clean()


class FolderPropertiesTests(TestCase):
    """Computed properties of ``InspectionFolder``."""

    def setUp(self):
        """Create a folder without any child."""
        self.folder = InspectionFolderFactory()
        self.kwargs = {"folder": self.folder, "created_by": self.folder.created_by}

    def test_counters_include_archived_children(self):
        """The counters count every visit and recommendation, archived ones included."""
        VisitInstanceFactory(**self.kwargs)
        VisitInstanceFactory(archived=True, **self.kwargs)
        RecommandationFactory(**self.kwargs)
        self.assertEqual(self.folder.count_all_visits, 2)
        self.assertEqual(self.folder.count_all_recommandations, 1)

    def test_get_latest_visit(self):
        """The latest visit is the last created one, None without visit."""
        self.assertIsNone(self.folder.get_latest_visit)
        VisitInstanceFactory(**self.kwargs)
        last = VisitInstanceFactory(**self.kwargs)
        self.assertEqual(self.folder.get_latest_visit, last)

    def test_next_visit_date(self):
        """The next visit date is the earliest date from today on, past dates ignored."""
        today = timezone.localdate()
        VisitInstanceFactory(due_date=today - timedelta(days=4), **self.kwargs)
        VisitInstanceFactory(due_date=today + timedelta(days=9), **self.kwargs)
        VisitInstanceFactory(due_date=today + timedelta(days=3), **self.kwargs)
        folder = InspectionFolder.objects.get(pk=self.folder.pk)
        self.assertEqual(folder.next_visit_date, today + timedelta(days=3))
        self.assertEqual(folder.days_until_next_visit, 3)

    def test_next_visit_date_without_upcoming_visit(self):
        """Without upcoming visit both properties are None."""
        self.assertIsNone(self.folder.next_visit_date)
        self.assertIsNone(self.folder.days_until_next_visit)

    def test_phase_progress(self):
        """The progress bar marks the previous phases done and the next ones todo."""
        folder = InspectionFolderFactory(current_phase=InspectionFolder.Phase.VISIT)
        progress = folder.phase_progress
        states = [step["state"] for step in progress["steps"]]
        self.assertEqual(states, ["done", "done", "current", "todo", "todo", "todo"])
        self.assertEqual(progress["style"], "width: 40%")
        self.assertEqual(progress["steps"][-1]["style"], "left: 100%")
        self.assertEqual(progress["steps"][0]["label"], "Création")

    def test_phase_progress_of_the_last_phase(self):
        """A closed folder fills the whole bar."""
        folder = InspectionFolderFactory(current_phase=InspectionFolder.Phase.CLOSED)
        self.assertEqual(folder.phase_progress["style"], "width: 100%")

    def test_archived_phase_is_out_of_the_progress(self):
        """The ``ARCHIVED`` phase has no progress bar."""
        folder = InspectionFolderFactory(current_phase=InspectionFolder.Phase.ARCHIVED)
        self.assertIsNone(folder.phase_progress)

    def test_str(self):
        """The label shows the reference, the client and the phase."""
        self.assertIn(self.folder.reference, str(self.folder))
        self.assertIn(self.folder.company.name, str(self.folder))


class FolderDeletionTests(FolderTreeMixin, TestCase):
    """Deletion cascades: what a folder, a visit or a recommendation takes with it."""

    def test_deleting_the_folder_deletes_children_and_files(self):
        """The folder takes its visits, recommendations, medias and stored files."""
        storage = self.media.file.storage
        name = self.media.file.name
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            self.folder.delete()
        self.assertFalse(VisitInstance.objects.exists())
        self.assertFalse(Recommandation.objects.exists())
        self.assertFalse(Media.objects.exists())
        self.assertFalse(storage.exists(name))

    def test_deleting_a_visit_keeps_its_media_on_the_folder(self):
        """A media attached to a deleted visit stays, without visit."""
        media = MediaFactory(folder=self.folder, created_by=self.user, visit=self.visit)
        self.visit.delete()
        media.refresh_from_db()
        self.assertIsNone(media.visit)
        self.assertEqual(media.folder, self.folder)
        self.assertTrue(media.file.storage.exists(media.file.name))

    def test_deleting_a_recommandation_keeps_its_media_on_the_folder(self):
        """A media attached to a deleted recommendation stays, without it."""
        media = MediaFactory(
            folder=self.folder, created_by=self.user, recommandation=self.recommandation
        )
        self.recommandation.delete()
        media.refresh_from_db()
        self.assertIsNone(media.recommandation)
        self.assertTrue(media.file.storage.exists(media.file.name))

    def test_company_with_a_folder_cannot_be_deleted(self):
        """The client of a folder is protected, so the folder is never orphaned."""
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.folder.company.delete()

    def test_deleting_the_contact_keeps_the_folder(self):
        """Deleting the referent contact empties the field, the folder stays."""
        self.folder.contact.delete()
        self.folder.refresh_from_db()
        self.assertIsNone(self.folder.contact)


class FolderServicesTests(TestCase):
    """Services of ``inspections/services/inspectionfolder.py`` and recommendations.

    Data: ``me`` owns an active and an archived folder, ``other`` owns one folder.
    """

    @classmethod
    def setUpTestData(cls):
        """Create the folders of two users."""
        cls.me = UserFactory()
        cls.other = UserFactory()
        cls.company = CompanyFactory(created_by=cls.me, name="Acme Industries")
        cls.mine = InspectionFolderFactory(company=cls.company, created_by=cls.me)
        cls.mine_archived = InspectionFolderFactory(
            company=cls.company,
            created_by=cls.me,
            archived=True,
            current_phase=InspectionFolder.Phase.REPORT,
        )
        cls.theirs = InspectionFolderFactory(created_by=cls.other)

    def request(self, **params):
        """Build a GET request of ``me`` with the given parameters.

        Args:
            **params: Query string parameters.

        Returns:
            The request.
        """
        request = RequestFactory().get("/dossiers/", params)
        request.user = self.me
        return request

    def test_filtered_folders_only_returns_the_user_folders(self):
        """The folders of other users never appear."""
        folders = set(get_filtered_folders(self.request()))
        self.assertEqual(folders, {self.mine, self.mine_archived})

    def test_filtered_folders_by_query(self):
        """The search matches the reference and the company name."""
        self.assertEqual(
            set(get_filtered_folders(self.request(q="acme"))),
            {self.mine, self.mine_archived},
        )
        self.assertEqual(
            list(get_filtered_folders(self.request(q=self.mine.reference))), [self.mine]
        )
        self.assertFalse(get_filtered_folders(self.request(q="zzz-none")).exists())

    def test_filtered_folders_by_status(self):
        """``active`` and ``archived`` split the folders."""
        self.assertEqual(
            list(get_filtered_folders(self.request(status="active"))), [self.mine]
        )
        self.assertEqual(
            list(get_filtered_folders(self.request(status="archived"))),
            [self.mine_archived],
        )

    def test_filtered_folders_by_phase_and_company(self):
        """The phase and the company filters apply."""
        self.assertEqual(
            list(get_filtered_folders(self.request(phase="REPORT"))),
            [self.mine_archived],
        )
        other_company = CompanyFactory(created_by=self.me)
        self.assertFalse(
            get_filtered_folders(self.request(company=other_company.pk)).exists()
        )
        self.assertEqual(
            len(get_filtered_folders(self.request(company=self.company.pk))), 2
        )

    def test_filtered_folders_sort_whitelist(self):
        """An allowed sort is applied, any other value falls back to ``-updated_at``."""
        by_reference = get_filtered_folders(self.request(sort="reference"))
        self.assertEqual(
            [f.reference for f in by_reference],
            sorted([self.mine.reference, self.mine_archived.reference]),
        )
        for bad in ("created_by__password", "pk; DROP TABLE", ""):
            with self.subTest(sort=bad):
                qs = get_filtered_folders(self.request(sort=bad))
                self.assertEqual(list(qs.query.order_by), ["-updated_at"])

    def test_get_inspection_folder_by_id(self):
        """The owner gets the folder, another user gets a 404."""
        self.assertEqual(get_inspection_folder_by_id(self.mine.pk, self.me), self.mine)
        with self.assertRaises(Http404):
            get_inspection_folder_by_id(self.theirs.pk, self.me)
        with self.assertRaises(Http404):
            get_inspection_folder_by_id(self.mine.pk, self.other)

    def test_get_inspection_folders_by_user_is_active_only(self):
        """Only the active folders of the user are returned."""
        self.assertEqual(list(get_inspection_folders_by_user(self.me)), [self.mine])

    def test_get_company_folders_is_limited_to_the_user(self):
        """The folders of a company that belong to others are hidden, archived ones shown."""
        InspectionFolderFactory(company=self.company, created_by=self.other)
        folders = list(get_company_folders(self.company, self.me))
        self.assertEqual(set(folders), {self.mine, self.mine_archived})
        self.assertEqual(
            list(get_company_folders(self.company, self.other)),
            list(
                InspectionFolder.objects.filter(
                    created_by=self.other, company=self.company
                )
            ),
        )

    def test_get_recommandation_by_id(self):
        """The owner of the folder gets the recommendation, others a 404."""
        recommandation = RecommandationFactory(folder=self.mine, created_by=self.me)
        self.assertEqual(
            get_recommandation_by_id(recommandation.pk, self.me), recommandation
        )
        with self.assertRaises(Http404):
            get_recommandation_by_id(recommandation.pk, self.other)
