"""Tests for the ``VisitInstance`` model (inspections/models.py)."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inspections.models import VisitInstance
from inspections.tests.factories import SAMPLE_SCHEMA, VisitInstanceFactory


class VisitIsLateTests(TestCase):
    """``is_late``, ``days_until_due`` on visits with various dates and statuses."""

    def test_scheduled_with_past_date_is_late(self):
        """A planned visit whose date is over is late."""
        self.assertTrue(VisitInstanceFactory(late=True).is_late)

    def test_scheduled_today_is_not_late(self):
        """A visit planned today is not late yet."""
        visit = VisitInstanceFactory(due_date=timezone.localdate())
        self.assertFalse(visit.is_late)

    def test_future_visit_is_not_late(self):
        """A visit planned in the future is not late."""
        visit = VisitInstanceFactory(due_date=timezone.localdate() + timedelta(days=1))
        self.assertFalse(visit.is_late)

    def test_without_date_is_not_late(self):
        """A visit without date can never be late."""
        self.assertFalse(VisitInstanceFactory(due_date=None).is_late)

    def test_validated_visit_is_not_late(self):
        """A done visit is not late even if its date is over."""
        past = timezone.localdate() - timedelta(days=3)
        visit = VisitInstanceFactory(validated=True, due_date=past)
        self.assertFalse(visit.is_late)

    def test_stored_delay_status_is_still_late(self):
        """The legacy ``DELAY`` status is still considered late."""
        visit = VisitInstanceFactory(current_status=VisitInstance.Status.DELAY)
        self.assertTrue(visit.is_late)

    def test_days_until_due(self):
        """The number of days is negative once the date is over, None without date."""
        today = timezone.localdate()
        self.assertEqual(
            VisitInstanceFactory(due_date=today + timedelta(days=4)).days_until_due, 4
        )
        self.assertEqual(
            VisitInstanceFactory(due_date=today - timedelta(days=2)).days_until_due, -2
        )
        self.assertIsNone(VisitInstanceFactory(due_date=None).days_until_due)


class VisitPropertiesTests(TestCase):
    """``answers``, ``progress``, ``display_template_name``, ``template_is_available``."""

    def test_answers_property(self):
        """``answers`` reads ``data["answers"]`` and tolerates bad data."""
        visit = VisitInstanceFactory(data={"answers": {"f_mesure": 5}})
        self.assertEqual(visit.answers, {"f_mesure": 5})
        visit.data = {}
        self.assertEqual(visit.answers, {})
        visit.data = ["bad"]
        self.assertEqual(visit.answers, {})

    def test_progress_uses_the_snapshot(self):
        """The progress is computed from ``instance_schema`` and the answers."""
        visit = VisitInstanceFactory(data={"answers": {"f_mesure": 5}})
        self.assertEqual(visit.progress["done"], 1)
        self.assertEqual(visit.progress["total"], 5)

    def test_template_is_available_follows_the_template(self):
        """The template is available while it exists and is active."""
        visit = VisitInstanceFactory()
        self.assertTrue(visit.template_is_available)
        visit.template.archive(visit.created_by)
        visit.refresh_from_db()
        self.assertFalse(visit.template_is_available)
        visit.template = None
        self.assertFalse(visit.template_is_available)

    def test_display_template_name_fallbacks(self):
        """The stored name wins, then the template name, then a placeholder."""
        visit = VisitInstanceFactory(template_name="Nom figé")
        self.assertEqual(visit.display_template_name, "Nom figé")
        visit.template_name = ""
        self.assertEqual(visit.display_template_name, visit.template.name)
        visit.template = None
        self.assertEqual(visit.display_template_name, "Template supprimé")


class VisitSaveTests(TestCase):
    """``VisitInstance.save()`` validates the visit, except with ``update_fields``."""

    def test_invalid_answers_are_refused(self):
        """Saving an answer that does not fit the snapshot raises ValidationError."""
        with self.assertRaisesMessage(ValidationError, "Réponses invalides"):
            VisitInstanceFactory(data={"answers": {"f_mesure": 500}})

    def test_unknown_answer_is_refused(self):
        """Saving an answer for a field absent from the snapshot is refused."""
        with self.assertRaises(ValidationError):
            VisitInstanceFactory(data={"answers": {"nope": 1}})

    def test_invalid_snapshot_is_refused(self):
        """A snapshot that is not a valid schema is refused."""
        with self.assertRaises(ValidationError):
            VisitInstanceFactory(instance_schema={"sections": []})

    def test_data_must_be_an_object(self):
        """Visit data that is not a JSON object is refused."""
        with self.assertRaisesMessage(ValidationError, "objet JSON"):
            VisitInstanceFactory(data=["bad"])

    def test_empty_snapshot_is_taken_from_the_template(self):
        """A visit saved without structure copies the one of its template."""
        visit = VisitInstanceFactory(instance_schema={})
        self.assertEqual(visit.instance_schema, SAMPLE_SCHEMA)

    def test_empty_answers_are_dropped_on_save(self):
        """Empty values are cleaned out of the answers at save time."""
        visit = VisitInstanceFactory(data={"answers": {"f_observation": ""}})
        visit.refresh_from_db()
        self.assertEqual(visit.answers, {})

    def test_update_fields_skips_the_validation(self):
        """A partial save does not call ``full_clean()`` (e.g. archiving)."""
        visit = VisitInstanceFactory()
        visit.data = {"answers": {"f_mesure": 500}}
        visit.notes = "partial"
        visit.save(update_fields=["notes"])
        visit.refresh_from_db()
        self.assertEqual(visit.notes, "partial")
        self.assertEqual(visit.answers, {})
