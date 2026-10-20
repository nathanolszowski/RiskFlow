"""Tests for the visit services (inspections/services/visit.py)."""

from datetime import date, time, timedelta

from accounts.tests.factories import UserFactory
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from inspections.models import VisitInstance
from inspections.services.visit import (
    VisitLockedError,
    coerce_input,
    complete_visit,
    create_visit,
    get_first_incomplete_section,
    get_form_field,
    get_next_visit,
    get_visit_by_id,
    get_visits_for_folder,
    reopen_visit,
    save_answers,
    set_visit_done,
)
from inspections.tests.factories import (
    SAMPLE_SCHEMA,
    InspectionFolderFactory,
    VisitInstanceFactory,
    VisitTemplateFactory,
)
from inspections.validators import AnswersValidationError

FULL_ANSWERS = {
    "f_acces_libre": True,
    "f_observation": "RAS",
    "f_niveau": "moyen",
    "f_mesure": 20,
}


class CreateVisitTests(TestCase):
    """``create_visit`` with a folder and a template of the same owner.

    Data: ``folder`` and ``template`` share ``user`` as owner.
    """

    @classmethod
    def setUpTestData(cls):
        """Create the folder and a private template of the same user."""
        cls.folder = InspectionFolderFactory()
        cls.user = cls.folder.created_by
        cls.template = VisitTemplateFactory(created_by=cls.user)

    def test_visit_snapshots_the_template(self):
        """The visit copies the schema and the name, and starts without answers."""
        visit = create_visit(self.folder, self.template, date(2030, 1, 2), self.user)
        visit.refresh_from_db()
        self.assertEqual(visit.instance_schema, SAMPLE_SCHEMA)
        self.assertEqual(visit.template_name, self.template.name)
        self.assertEqual(visit.answers, {})
        self.assertEqual(visit.due_date, date(2030, 1, 2))
        self.assertEqual(visit.created_by, self.user)

    def test_due_time_is_stored(self):
        """The appointment time is kept."""
        visit = create_visit(
            self.folder, self.template, None, self.user, due_time=time(9, 30)
        )
        self.assertEqual(visit.due_time, time(9, 30))

    def test_archived_template_is_refused(self):
        """An archived template cannot start a new visit."""
        self.template.archive(self.user)
        with self.assertRaisesMessage(ValidationError, "archivé"):
            create_visit(self.folder, self.template, None, self.user)

    def test_private_template_of_another_user_is_refused(self):
        """A private template belonging to someone else is not available."""
        foreign = VisitTemplateFactory()
        with self.assertRaisesMessage(ValidationError, "pas disponible"):
            create_visit(self.folder, foreign, None, self.user)
        self.assertFalse(VisitInstance.objects.exists())

    def test_shared_template_of_another_user_is_accepted(self):
        """A template shared by someone else can be used."""
        shared = VisitTemplateFactory(shared_template=True)
        visit = create_visit(self.folder, shared, None, self.user)
        self.assertEqual(visit.template, shared)


class SnapshotIndependenceTests(TestCase):
    """A visit does not depend on its template once created."""

    def setUp(self):
        """Create a visit and remember its snapshot."""
        self.visit = VisitInstanceFactory()
        self.template = self.visit.template
        self.user = self.visit.created_by

    def test_editing_the_template_leaves_the_visit_unchanged(self):
        """Changing the template schema does not change the visit schema."""
        self.template.schema["sections"].pop()
        self.template.save()
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.instance_schema, SAMPLE_SCHEMA)

    def test_archiving_the_template_leaves_the_visit_unchanged(self):
        """Archiving the template keeps the snapshot, but the template is unavailable."""
        self.template.archive(self.user)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.instance_schema, SAMPLE_SCHEMA)
        self.assertFalse(self.visit.template_is_available)

    def test_deleting_the_template_keeps_snapshot_and_name(self):
        """After deletion the template link is empty but the visit still displays its name."""
        name = self.template.name
        self.template.delete()
        self.visit.refresh_from_db()
        self.assertIsNone(self.visit.template)
        self.assertEqual(self.visit.instance_schema, SAMPLE_SCHEMA)
        self.assertEqual(self.visit.display_template_name, name)


class SaveAnswersTests(TestCase):
    """``save_answers``: on-the-fly saving of one or several answers."""

    def setUp(self):
        """Create a visit without answers."""
        self.visit = VisitInstanceFactory()
        self.user = self.visit.created_by

    def test_two_calls_accumulate_answers(self):
        """Answers saved by two calls on two fields are both kept."""
        save_answers(self.visit.pk, self.user, {"f_acces_libre": True})
        save_answers(self.visit.pk, self.user, {"f_niveau": "faible"})
        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.answers, {"f_acces_libre": True, "f_niveau": "faible"}
        )

    def test_empty_value_removes_the_answer(self):
        """Saving an empty value deletes the existing answer."""
        save_answers(self.visit.pk, self.user, {"f_observation": "texte"})
        save_answers(self.visit.pk, self.user, {"f_observation": ""})
        self.visit.refresh_from_db()
        self.assertNotIn("f_observation", self.visit.answers)

    def test_revision_increments_by_one_per_call(self):
        """Each call adds exactly one to the revision."""
        for expected in (1, 2, 3):
            result = save_answers(self.visit.pk, self.user, {"f_mesure": expected})
            self.assertEqual(result.revision, expected)

    def test_updated_by_is_recorded(self):
        """The user who saved the answers becomes ``updated_by``."""
        other = UserFactory()
        save_answers(self.visit.pk, other, {"f_mesure": 5})
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.updated_by, other)

    def test_returns_the_visit_with_its_progress(self):
        """The returned visit carries the new answers, ready for the progress."""
        visit = save_answers(self.visit.pk, self.user, {"f_mesure": 5})
        self.assertEqual(visit.progress["done"], 1)

    def test_invalid_value_leaves_the_database_unchanged(self):
        """An invalid value raises AnswersValidationError and nothing is saved."""
        save_answers(self.visit.pk, self.user, {"f_mesure": 5})
        with self.assertRaises(AnswersValidationError):
            save_answers(
                self.visit.pk, self.user, {"f_niveau": "faible", "f_mesure": 500}
            )
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.answers, {"f_mesure": 5})
        self.assertEqual(self.visit.revision, 1)

    def test_validated_visit_is_locked(self):
        """A visit marked done refuses new answers."""
        visit = VisitInstanceFactory(validated=True)
        with self.assertRaises(VisitLockedError):
            save_answers(visit.pk, visit.created_by, {"f_mesure": 5})

    def test_archived_visit_is_locked(self):
        """An archived visit refuses new answers."""
        visit = VisitInstanceFactory(archived=True)
        with self.assertRaises(VisitLockedError):
            save_answers(visit.pk, visit.created_by, {"f_mesure": 5})


class CompleteVisitTests(TestCase):
    """``complete_visit``: check of the required fields at the end of the filling."""

    def test_missing_required_fields_are_listed(self):
        """The error lists the id of every missing required field."""
        visit = VisitInstanceFactory()
        save_answers(visit.pk, visit.created_by, {"f_acces_libre": True})
        with self.assertRaises(AnswersValidationError) as ctx:
            complete_visit(visit.pk, visit.created_by)
        self.assertEqual(
            set(ctx.exception.field_errors),
            {"f_observation", "f_niveau", "f_mesure"},
        )

    def test_complete_visit_keeps_its_status(self):
        """A complete visit passes and its status is not changed."""
        visit = VisitInstanceFactory(data={"answers": FULL_ANSWERS})
        result = complete_visit(visit.pk, visit.created_by)
        self.assertEqual(result.current_status, VisitInstance.Status.SCHEDULED)
        visit.refresh_from_db()
        self.assertEqual(visit.current_status, VisitInstance.Status.SCHEDULED)

    def test_archived_visit_is_locked(self):
        """An archived visit cannot be completed."""
        visit = VisitInstanceFactory(archived=True)
        with self.assertRaises(VisitLockedError):
            complete_visit(visit.pk, visit.created_by)


class VisitStatusTests(TestCase):
    """``set_visit_done`` and ``reopen_visit``."""

    def setUp(self):
        """Create a scheduled visit."""
        self.visit = VisitInstanceFactory()
        self.user = self.visit.created_by

    def test_done_validates_and_dates_the_visit(self):
        """Ticking done sets VALIDATED and ``completed_at``."""
        set_visit_done(self.visit, self.user, True)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.current_status, VisitInstance.Status.VALIDATED)
        self.assertIsNotNone(self.visit.completed_at)

    def test_second_done_keeps_the_first_completion_date(self):
        """Ticking done twice does not move ``completed_at``."""
        set_visit_done(self.visit, self.user, True)
        first = self.visit.completed_at
        set_visit_done(self.visit, self.user, True)
        self.assertEqual(self.visit.completed_at, first)

    def test_not_done_plans_the_visit_again(self):
        """Unticking returns to SCHEDULED and clears ``completed_at``."""
        set_visit_done(self.visit, self.user, True)
        set_visit_done(self.visit, self.user, False)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.current_status, VisitInstance.Status.SCHEDULED)
        self.assertIsNone(self.visit.completed_at)

    def test_set_done_on_archived_visit_is_refused(self):
        """An archived visit cannot be ticked."""
        visit = VisitInstanceFactory(archived=True)
        with self.assertRaises(VisitLockedError):
            set_visit_done(visit, visit.created_by, True)

    def test_reopen_returns_to_scheduled(self):
        """Reopening a done visit plans it again without completion date."""
        visit = VisitInstanceFactory(validated=True)
        reopen_visit(visit, visit.created_by)
        visit.refresh_from_db()
        self.assertEqual(visit.current_status, VisitInstance.Status.SCHEDULED)
        self.assertIsNone(visit.completed_at)

    def test_reopen_archived_visit_is_refused(self):
        """An archived visit cannot be reopened."""
        visit = VisitInstanceFactory(archived=True, validated=True)
        with self.assertRaises(VisitLockedError):
            reopen_visit(visit, visit.created_by)


class CoerceInputTests(SimpleTestCase):
    """``coerce_input``: conversion of the posted strings (no database needed)."""

    boolean = {"type": "boolean"}
    number = {"type": "number"}
    text = {"type": "text"}

    def test_empty_means_no_answer(self):
        """None and an empty string give None, for every type."""
        for field in (self.boolean, self.number, self.text):
            for raw in (None, ""):
                with self.subTest(type=field["type"], raw=raw):
                    self.assertIsNone(coerce_input(field, raw))

    def test_boolean_values(self):
        """``true`` and ``false`` are converted to booleans."""
        self.assertIs(coerce_input(self.boolean, "true"), True)
        self.assertIs(coerce_input(self.boolean, "false"), False)

    def test_boolean_rejects_other_strings(self):
        """Checkbox-style values such as ``on`` are not accepted by the form contract."""
        for raw in ("on", "1", "oui"):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                coerce_input(self.boolean, raw)

    def test_number_integer_and_decimal(self):
        """Integers stay integers, a comma is accepted as decimal separator."""
        self.assertEqual(coerce_input(self.number, "12"), 12)
        self.assertIsInstance(coerce_input(self.number, "12"), int)
        self.assertEqual(coerce_input(self.number, "12,5"), 12.5)
        self.assertEqual(coerce_input(self.number, "12.5"), 12.5)
        self.assertIsInstance(coerce_input(self.number, "12.0"), int)

    def test_unreadable_number_is_refused(self):
        """Text, ``nan`` and ``inf`` are not numbers."""
        for raw in ("abc", "nan", "inf", "1,2,3"):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                coerce_input(self.number, raw)

    def test_text_is_returned_as_is(self):
        """Text and select values are not modified."""
        self.assertEqual(coerce_input(self.text, " bonjour "), " bonjour ")
        self.assertEqual(coerce_input({"type": "select"}, "faible"), "faible")


class FormHelpersTests(TestCase):
    """``get_form_field`` and ``get_first_incomplete_section``."""

    def setUp(self):
        """Create a visit without answers."""
        self.visit = VisitInstanceFactory()

    def test_get_form_field_reads_the_snapshot(self):
        """A field is found by id in the visit snapshot."""
        field = get_form_field(self.visit, "f_mesure")
        self.assertEqual(field["type"], "number")
        self.assertEqual(field["unit"], "°C")

    def test_get_form_field_unknown_id(self):
        """An unknown id gives None."""
        self.assertIsNone(get_form_field(self.visit, "nope"))

    def test_first_incomplete_section_follows_the_answers(self):
        """The first section with a missing required field is returned, then None."""
        self.assertEqual(get_first_incomplete_section(self.visit), "s_general")
        self.visit.data = {"answers": {"f_acces_libre": True, "f_observation": "x"}}
        self.assertEqual(get_first_incomplete_section(self.visit), "s_mesures")
        self.visit.data = {"answers": FULL_ANSWERS}
        self.assertIsNone(get_first_incomplete_section(self.visit))


class VisitQueriesTests(TestCase):
    """Getters of visits: next visit, list of a folder and filtered access."""

    @classmethod
    def setUpTestData(cls):
        """Create a folder with a late, a future, a done and an archived visit."""
        cls.folder = InspectionFolderFactory()
        cls.user = cls.folder.created_by
        today = timezone.localdate()
        kwargs = {"folder": cls.folder, "created_by": cls.user}
        cls.later = VisitInstanceFactory(due_date=today + timedelta(days=10), **kwargs)
        cls.sooner = VisitInstanceFactory(due_date=today + timedelta(days=2), **kwargs)
        cls.done = VisitInstanceFactory(
            due_date=today - timedelta(days=5), validated=True, **kwargs
        )
        cls.archived = VisitInstanceFactory(due_date=today, archived=True, **kwargs)

    def test_next_visit_is_the_earliest_pending_active_one(self):
        """Done and archived visits are skipped."""
        self.assertEqual(get_next_visit(self.folder), self.sooner)

    def test_next_visit_without_pending_visit(self):
        """A folder without pending visit has no next visit."""
        self.assertIsNone(get_next_visit(InspectionFolderFactory()))

    def test_visits_of_a_folder_by_status(self):
        """``active`` lists the active visits, newest date first, ``archived`` the others."""
        active = list(get_visits_for_folder(self.folder, "active"))
        self.assertEqual(active, [self.later, self.sooner, self.done])
        self.assertEqual(
            list(get_visits_for_folder(self.folder, "archived")), [self.archived]
        )

    def test_any_other_status_lists_the_active_visits(self):
        """Known gap: ``all`` is not a supported status, it behaves like ``active``."""
        self.assertEqual(
            list(get_visits_for_folder(self.folder, "all")),
            list(get_visits_for_folder(self.folder, "active")),
        )

    def test_get_visit_by_id_of_the_owner(self):
        """The owner of the folder gets the visit."""
        self.assertEqual(get_visit_by_id(self.later.pk, self.user), self.later)

    def test_get_visit_by_id_of_another_user_is_404(self):
        """A visit of someone else's folder is not found."""
        with self.assertRaises(Http404):
            get_visit_by_id(self.later.pk, UserFactory())
