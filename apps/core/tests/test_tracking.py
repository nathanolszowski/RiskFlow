"""Tests for ``TrackingModel`` and the generic tracked-instance helpers.

Covers ``core/models.py``, ``core/services/__init__.py`` and
``inspections/services/inspectionfolder.py::create_tracked_instance``. ``Contact``
is the model used for the generic behaviour: it has no cascade of its own.
"""

from accounts.tests.factories import UserFactory
from crm.models import Contact
from crm.tests.factories import CompanyFactory, ContactFactory
from django import forms
from django.test import TestCase
from inspections.models import InspectionFolder
from inspections.services import inspectionfolder as folder_services
from inspections.tests.factories import InspectionFolderFactory

from core.services import (
    archive_tracked_instance,
    create_tracked_instance,
    delete_archived_instance,
    hard_delete_instance,
    unarchive_tracked_instance,
    update_tracked_instance,
)


class ContactForm(forms.ModelForm):
    """Minimal model form of ``Contact`` used to feed the creation helpers."""

    class Meta:
        """Bind the form to ``Contact``."""

        model = Contact
        fields = ["company", "first_name", "last_name", "position"]


class FolderForm(forms.ModelForm):
    """Minimal model form of ``InspectionFolder`` used to feed the creation helper."""

    class Meta:
        """Bind the form to ``InspectionFolder``."""

        model = InspectionFolder
        fields = ["company", "contact"]


class ArchiveMethodsTests(TestCase):
    """``TrackingModel.archive()`` and ``unarchive()`` on a contact."""

    def setUp(self):
        """Create a contact and a user who archives it."""
        self.contact = ContactFactory()
        self.user = UserFactory()

    def test_archive_sets_the_tracking_fields(self):
        """Archiving deactivates the record and records the date and the user."""
        self.contact.archive(self.user)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_active)
        self.assertIsNotNone(self.contact.archived_at)
        self.assertEqual(self.contact.archived_by, self.user)
        self.assertEqual(self.contact.updated_by, self.user)

    def test_archive_without_user(self):
        """Archiving without a user leaves ``archived_by`` empty."""
        self.contact.archive()
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_active)
        self.assertIsNone(self.contact.archived_by)

    def test_unarchive_clears_the_archive_fields(self):
        """Unarchiving reactivates the record and clears the archive date and user."""
        self.contact.archive(self.user)
        self.contact.unarchive(self.user)
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.is_active)
        self.assertIsNone(self.contact.archived_at)
        self.assertIsNone(self.contact.archived_by)
        self.assertEqual(self.contact.updated_by, self.user)

    def test_hooks_are_called_with_the_right_arguments(self):
        """``archive`` calls ``cascade_archive`` and ``unarchive`` passes the old date."""
        calls = []
        self.contact.cascade_archive = lambda user=None: calls.append(("a", user))
        self.contact.cascade_unarchive = lambda archived_at=None, user=None: (
            calls.append(("u", archived_at, user))
        )
        self.contact.archive(self.user)
        archived_at = self.contact.archived_at
        self.contact.unarchive(self.user)
        self.assertEqual(calls, [("a", self.user), ("u", archived_at, self.user)])

    def test_created_by_is_mandatory(self):
        """A tracked record cannot be created without ``created_by``."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Contact.objects.create(
                company=CompanyFactory(),
                first_name="A",
                last_name="B",
                position="C",
            )


class TrackedInstanceHelpersTests(TestCase):
    """Generic helpers of ``core.services`` on contacts."""

    def setUp(self):
        """Create a user, a company and a contact."""
        self.user = UserFactory()
        self.company = CompanyFactory()
        self.contact = ContactFactory(company=self.company)

    def test_create_tracked_instance(self):
        """A valid form creates the record with ``created_by`` and ``updated_by``."""
        form = ContactForm(
            {
                "company": self.company.pk,
                "first_name": "Ada",
                "last_name": "Lovelace",
                "position": "Directrice",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        contact = create_tracked_instance(form, self.user)
        contact.refresh_from_db()
        self.assertEqual(contact.created_by, self.user)
        self.assertEqual(contact.updated_by, self.user)

    def test_update_tracked_instance_writes_only_the_given_fields(self):
        """Only the given fields and the tracking ones are written."""
        original_last_name = self.contact.last_name
        stale = Contact.objects.get(pk=self.contact.pk)
        stale.last_name = "Modifié en mémoire seulement"
        update_tracked_instance(stale, self.user, first_name="Nouveau")
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.first_name, "Nouveau")
        self.assertEqual(self.contact.last_name, original_last_name)
        self.assertEqual(self.contact.updated_by, self.user)

    def test_archive_and_unarchive_tracked_instance(self):
        """The helpers archive and restore a record without calling the cascade."""
        archive_tracked_instance(self.contact, self.user)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_active)
        self.assertEqual(self.contact.archived_by, self.user)
        self.assertIsNotNone(self.contact.archived_at)
        unarchive_tracked_instance(self.contact, self.user)
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.is_active)
        self.assertIsNone(self.contact.archived_at)
        self.assertIsNone(self.contact.archived_by)

    def test_archive_tracked_instance_does_not_cascade(self):
        """Unlike ``archive()``, the helper leaves the children untouched."""
        folder = InspectionFolderFactory()
        archive_tracked_instance(folder.company, folder.created_by)
        folder.contact.refresh_from_db()
        self.assertTrue(folder.contact.is_active)

    def test_hard_delete_instance_deletes_an_active_record(self):
        """The hard delete does not check the state of the record."""
        hard_delete_instance(self.contact)
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_delete_archived_instance_refuses_an_active_record(self):
        """An active record cannot be deleted permanently."""
        with self.assertRaises(ValueError):
            delete_archived_instance(self.contact)
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_delete_archived_instance_deletes_an_archived_record(self):
        """An archived record is deleted permanently."""
        self.contact.archive(self.user)
        delete_archived_instance(self.contact)
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())


class FolderCreateTrackedInstanceTests(TestCase):
    """``inspections.services.inspectionfolder.create_tracked_instance``."""

    def setUp(self):
        """Create a company with a contact and two users."""
        self.contact = ContactFactory()
        self.company = self.contact.company
        self.user = UserFactory()
        self.data = {"company": self.company.pk, "contact": self.contact.pk}

    def test_sets_created_by_when_empty(self):
        """Without ``created_by`` on the instance, the given user is recorded."""
        form = FolderForm(self.data)
        self.assertTrue(form.is_valid(), form.errors)
        folder = folder_services.create_tracked_instance(form, self.user)
        self.assertEqual(folder.created_by, self.user)
        self.assertTrue(folder.reference.startswith("DOS-"))

    def test_keeps_an_existing_created_by(self):
        """An instance that already has a creator keeps it."""
        form = FolderForm(self.data)
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.created_by = self.company.created_by
        folder = folder_services.create_tracked_instance(form, self.user)
        self.assertEqual(folder.created_by, self.company.created_by)

    def test_contact_of_another_company_is_refused(self):
        """The form rejects a contact of another client (``InspectionFolder.clean``)."""
        other = ContactFactory()
        form = FolderForm({"company": self.company.pk, "contact": other.pk})
        self.assertFalse(form.is_valid())
        self.assertIn("contact", form.errors)
