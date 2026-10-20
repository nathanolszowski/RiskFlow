"""Tests for the visit form views (inspections/views_visit_form.py) and the visit views.

Covers the form pages, the on-the-fly saving, the completion and reopening, and the
visit creation, planning and "done" views of ``inspections/views.py``.
"""

from datetime import date

from core.tests.helpers import HtmxClientMixin
from django.test import TestCase
from django.urls import reverse

from inspections.models import VisitInstance
from inspections.services.template import get_usable_templates
from inspections.tests.factories import (
    SAMPLE_SCHEMA,
    InspectionFolderFactory,
    VisitInstanceFactory,
    VisitTemplateFactory,
)

FULL_ANSWERS = {
    "f_acces_libre": True,
    "f_observation": "RAS",
    "f_niveau": "moyen",
    "f_mesure": 20,
}
OOB_IDS = ("visit-progress", "visit-nav", "visit-remaining", "save-status")


class VisitFormTestCase(HtmxClientMixin, TestCase):
    """Base class: a visit of the logged-in ``owner``, without answers."""

    def setUp(self):
        """Create the folder and the visit of the owner."""
        super().setUp()
        self.visit = VisitInstanceFactory(
            created_by=self.owner, folder__created_by=self.owner
        )
        self.folder = self.visit.folder

    def url(self, name, *args):
        """Reverse an ``inspections`` URL.

        Args:
            name: URL name without the namespace.
            *args: URL arguments.

        Returns:
            The URL.
        """
        return reverse(f"inspections:{name}", args=args)

    def save(self, field_id, value, section_id="s_general", visit=None):
        """Post one answer like the form does.

        Args:
            field_id: Id of the field.
            value: Posted string.
            section_id: Section being displayed.
            visit: Visit to post to, the base one by default.

        Returns:
            The response.
        """
        visit = visit or self.visit
        return self.htmx_post(
            self.url("visit_save_answers", visit.pk),
            {"field_id": field_id, "value": value, "section_id": section_id},
        )


class VisitFormPageTests(VisitFormTestCase):
    """``visit_form`` and ``visit_form_section``."""

    def test_form_opens_on_the_first_section(self):
        """The page shows the first section of the snapshot and the progress."""
        response = self.client.get(self.url("visit_form", self.visit.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["section"]["id"], "s_general")
        self.assertEqual(
            [f["id"] for f in response.context["fields"]],
            ["f_acces_libre", "f_observation"],
        )
        self.assertFalse(response.context["readonly"])
        self.assertEqual(response.context["progress"]["total"], 5)

    def test_section_parameter_opens_another_section(self):
        """``?section=`` selects the section to open, an unknown id falls back to the first."""
        url = self.url("visit_form", self.visit.pk)
        response = self.client.get(url, {"section": "s_mesures"})
        self.assertEqual(response.context["section"]["id"], "s_mesures")
        self.assertEqual(response.context["previous_section_id"], "s_general")
        self.assertIsNone(response.context["next_section_id"])
        response = self.client.get(url, {"section": "nope"})
        self.assertEqual(response.context["section"]["id"], "s_general")

    def test_form_reads_the_snapshot_not_the_template(self):
        """Changing the template after the creation does not change the form."""
        self.visit.template.schema["sections"].pop()
        self.visit.template.save()
        response = self.client.get(self.url("visit_form", self.visit.pk))
        self.assertEqual(response.context["section_count"], 2)

    def test_existing_answers_are_shown(self):
        """The saved value of a field is in the context."""
        VisitInstance.objects.filter(pk=self.visit.pk).update(
            data={"answers": {"f_observation": "texte"}}
        )
        response = self.client.get(self.url("visit_form", self.visit.pk))
        self.assertContains(response, "texte")

    def test_validated_and_archived_visits_are_read_only(self):
        """A done or archived visit opens in read-only mode."""
        for kwargs in ({"validated": True}, {"archived": True}):
            with self.subTest(kwargs=kwargs):
                visit = VisitInstanceFactory(
                    created_by=self.owner, folder=self.folder, **kwargs
                )
                response = self.client.get(self.url("visit_form", visit.pk))
                self.assertTrue(response.context["readonly"])

    def test_section_fragment(self):
        """The section view returns the fragment of the section with out-of-band navigation."""
        response = self.htmx_get(
            self.url("visit_form_section", self.visit.pk, "s_mesures")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["oob"])
        self.assertContains(response, "Niveau de risque")
        self.assertNotContains(response, "<html")

    def test_visit_form_rejects_post(self):
        """The form page is read-only: POST is refused."""
        self.assertEqual(
            self.client.post(self.url("visit_form", self.visit.pk)).status_code, 405
        )


class SaveAnswersViewTests(VisitFormTestCase):
    """``visit_save_answers``: 200, 404, 409 and 422."""

    def test_valid_answer_is_saved_with_out_of_band_fragments(self):
        """A valid value answers 200 with progress, navigation and saved indicator."""
        response = self.save("f_acces_libre", "true")
        self.assertEqual(response.status_code, 200)
        for element_id in OOB_IDS:
            self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'hx-swap-oob="true"')
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.answers, {"f_acces_libre": True})

    def test_revision_is_incremented_by_each_save(self):
        """Each save adds one to the revision."""
        self.save("f_observation", "a")
        self.save("f_observation", "ab")
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.revision, 2)
        self.assertEqual(self.visit.answers, {"f_observation": "ab"})

    def test_progress_fragment_follows_the_answers(self):
        """The progress counters of the answer take the new answer into account."""
        response = self.save("f_acces_libre", "false")
        self.assertEqual(response.context["progress"]["done"], 1)

    def test_comma_decimal_is_accepted(self):
        """A number typed with a comma is stored as a float."""
        self.save("f_mesure", "12,5", section_id="s_mesures")
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.answers, {"f_mesure": 12.5})

    def test_empty_value_removes_the_answer(self):
        """Posting an empty value clears the answer."""
        self.save("f_observation", "texte")
        response = self.save("f_observation", "")
        self.assertEqual(response.status_code, 200)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.answers, {})

    def test_value_out_of_bounds_is_422_and_nothing_is_saved(self):
        """A refused value answers 422 with the message under the field."""
        self.save("f_mesure", "50", section_id="s_mesures")
        response = self.save("f_mesure", "500", section_id="s_mesures")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'id="err-f_mesure"', status_code=422)
        self.assertContains(response, "au plus 100", status_code=422)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.answers, {"f_mesure": 50})
        self.assertEqual(self.visit.revision, 1)

    def test_unreadable_number_is_422(self):
        """A string that is not a number is refused with a message."""
        response = self.save("f_mesure", "abc", section_id="s_mesures")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Un nombre est attendu", status_code=422)

    def test_invalid_select_option_is_422(self):
        """An option outside the list is refused."""
        response = self.save("f_niveau", "extrême", section_id="s_mesures")
        self.assertEqual(response.status_code, 422)

    def test_unknown_field_is_404(self):
        """A field absent from the snapshot answers 404."""
        response = self.save("nope", "1")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Champ inconnu", status_code=404)

    def test_validated_visit_is_409(self):
        """A done visit refuses new answers."""
        visit = VisitInstanceFactory(
            validated=True, created_by=self.owner, folder=self.folder
        )
        self.assertEqual(self.save("f_observation", "x", visit=visit).status_code, 409)

    def test_archived_visit_is_409(self):
        """An archived visit refuses new answers."""
        visit = VisitInstanceFactory(
            archived=True, created_by=self.owner, folder=self.folder
        )
        response = self.save("f_observation", "x", visit=visit)
        self.assertEqual(response.status_code, 409)
        visit.refresh_from_db()
        self.assertEqual(visit.answers, {})

    def test_get_is_refused(self):
        """The save view only accepts POST."""
        self.assertEqual(
            self.client.get(self.url("visit_save_answers", self.visit.pk)).status_code,
            405,
        )


class CompleteAndReopenTests(VisitFormTestCase):
    """``visit_complete`` and ``visit_reopen``."""

    def test_missing_required_fields_re_render_the_form(self):
        """A visit with missing fields answers 422 on the first incomplete section."""
        self.save("f_acces_libre", "true")
        self.save("f_observation", "ok")
        response = self.htmx_post(self.url("visit_complete", self.visit.pk))
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.context["show_errors"])
        self.assertEqual(response.context["section"]["id"], "s_mesures")
        self.assertTrue(all(f["error"] for f in response.context["fields"][:2]))
        self.assertContains(response, "obligatoire", status_code=422)

    def test_complete_visit_redirects_to_the_folder_without_changing_the_status(self):
        """A complete visit goes back to the visits tab and keeps its status."""
        VisitInstance.objects.filter(pk=self.visit.pk).update(
            data={"answers": FULL_ANSWERS}
        )
        response = self.htmx_post(self.url("visit_complete", self.visit.pk))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            response["HX-Redirect"],
            self.url("folder_detail", self.folder.pk) + "?tab=visit",
        )
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.current_status, VisitInstance.Status.SCHEDULED)
        self.assertIsNone(self.visit.completed_at)

    def test_complete_archived_visit_is_409(self):
        """An archived visit cannot be completed."""
        visit = VisitInstanceFactory(
            archived=True, created_by=self.owner, folder=self.folder
        )
        self.assertEqual(
            self.htmx_post(self.url("visit_complete", visit.pk)).status_code, 409
        )

    def test_reopen_plans_the_visit_again_and_opens_its_form(self):
        """Reopening a done visit sets it back to SCHEDULED and redirects to the form."""
        visit = VisitInstanceFactory(
            validated=True, created_by=self.owner, folder=self.folder
        )
        response = self.htmx_post(self.url("visit_reopen", visit.pk))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], self.url("visit_form", visit.pk))
        visit.refresh_from_db()
        self.assertEqual(visit.current_status, VisitInstance.Status.SCHEDULED)
        self.assertIsNone(visit.completed_at)

    def test_reopen_archived_visit_is_404(self):
        """An archived visit cannot be reopened (404)."""
        visit = VisitInstanceFactory(
            archived=True, created_by=self.owner, folder=self.folder
        )
        self.assertEqual(
            self.htmx_post(self.url("visit_reopen", visit.pk)).status_code, 404
        )


class ToggleDoneTests(VisitFormTestCase):
    """``visit_toggle_done``: the "done" checkbox of the visits tab."""

    def test_tick_marks_the_visit_done_and_returns_the_tab(self):
        """A ticked box validates the visit and re-renders the visits tab."""
        response = self.htmx_post(
            self.url("visit_toggle_done", self.visit.pk), {"done": "on"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inspections/partials/tabs/tab_visit.html")
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.current_status, VisitInstance.Status.VALIDATED)
        self.assertIsNotNone(self.visit.completed_at)

    def test_untick_plans_the_visit_again(self):
        """An unticked box (no ``done`` posted) sets the visit back to SCHEDULED."""
        visit = VisitInstanceFactory(
            validated=True, created_by=self.owner, folder=self.folder
        )
        self.htmx_post(self.url("visit_toggle_done", visit.pk))
        visit.refresh_from_db()
        self.assertEqual(visit.current_status, VisitInstance.Status.SCHEDULED)

    def test_archived_visit_is_409(self):
        """An archived visit cannot be ticked."""
        visit = VisitInstanceFactory(
            archived=True, created_by=self.owner, folder=self.folder
        )
        response = self.htmx_post(
            self.url("visit_toggle_done", visit.pk), {"done": "on"}
        )
        self.assertEqual(response.status_code, 409)


class VisitCreateTests(VisitFormTestCase):
    """``visit_create``: preparation of a visit from a usable template."""

    def setUp(self):
        """Create the templates around the visit: shared, private of others, archived."""
        super().setUp()
        self.shared = VisitTemplateFactory(shared=True)
        self.foreign_private = VisitTemplateFactory()
        self.archived = VisitTemplateFactory(created_by=self.owner, archived=True)
        self.url_create = self.url("visit_create", self.folder.pk)

    def test_modal_offers_the_usable_templates_only(self):
        """The modal proposes my templates and the shared ones, not archived or foreign private."""
        response = self.htmx_get(self.url_create)
        self.assertEqual(response.status_code, 200)
        offered = set(response.context["form"].fields["template"].queryset)
        self.assertEqual(offered, set(get_usable_templates(self.owner)))
        self.assertIn(self.shared, offered)
        self.assertIn(self.visit.template, offered)
        self.assertNotIn(self.foreign_private, offered)
        self.assertNotIn(self.archived, offered)

    def test_modal_preselects_the_template_and_today(self):
        """``?template=`` and today's date are the initial values."""
        response = self.htmx_get(self.url_create, {"template": self.shared.pk})
        self.assertEqual(
            str(response.context["form"].initial["template"]), str(self.shared.pk)
        )
        self.assertIsInstance(response.context["form"].initial["due_date"], date)

    def test_valid_post_creates_the_visit_with_a_snapshot(self):
        """A valid POST creates the visit and returns the tab, closing the modal."""
        response = self.htmx_post(
            self.url_create,
            {"template": self.shared.pk, "due_date": "2030-05-06", "due_time": "09:30"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "closeModal")
        self.assertTemplateUsed(response, "inspections/partials/tabs/tab_visit.html")
        visit = self.folder.visits.exclude(pk=self.visit.pk).get()
        self.assertEqual(visit.instance_schema, SAMPLE_SCHEMA)
        self.assertEqual(visit.template, self.shared)
        self.assertEqual(
            (visit.due_date, str(visit.due_time)), (date(2030, 5, 6), "09:30:00")
        )
        self.assertEqual(visit.created_by, self.owner)

    def test_invalid_post_is_422_and_targets_the_modal(self):
        """A missing date re-renders the modal (422) and retargets it."""
        response = self.htmx_post(self.url_create, {"template": self.shared.pk})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.assertEqual(response["HX-Reswap"], "innerHTML")
        self.assertContains(response, "Indiquez la date de la visite", status_code=422)
        self.assertEqual(self.folder.visits.count(), 1)

    def test_unusable_template_is_refused(self):
        """A foreign private template cannot be chosen."""
        response = self.htmx_post(
            self.url_create,
            {"template": self.foreign_private.pk, "due_date": "2030-05-06"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "pas disponible", status_code=422)
        self.assertEqual(self.folder.visits.count(), 1)

    def test_archived_folder_is_409(self):
        """No visit can be prepared on an archived folder."""
        folder = InspectionFolderFactory(created_by=self.owner, archived=True)
        response = self.htmx_get(self.url("visit_create", folder.pk))
        self.assertEqual(response.status_code, 409)
        response = self.htmx_post(
            self.url("visit_create", folder.pk),
            {"template": self.shared.pk, "due_date": "2030-05-06"},
        )
        self.assertEqual(response.status_code, 409)


class VisitUpdateTests(VisitFormTestCase):
    """``visit_update``: the planning modal (date, time and notes)."""

    def test_get_renders_the_modal(self):
        """The modal is pre-filled with the visit."""
        response = self.htmx_get(self.url("visit_update", self.visit.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].instance, self.visit)
        self.assertEqual(
            set(response.context["form"].fields), {"due_date", "due_time", "notes"}
        )

    def test_valid_post_updates_the_planning_and_closes_the_modal(self):
        """The planning is saved, the status is not touched."""
        response = self.htmx_post(
            self.url("visit_update", self.visit.pk),
            {"due_date": "2031-01-02", "due_time": "14:00", "notes": "Prévoir EPI"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "closeModal")
        self.assertTemplateUsed(response, "inspections/partials/tabs/tab_visit.html")
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.due_date, date(2031, 1, 2))
        self.assertEqual(self.visit.notes, "Prévoir EPI")
        self.assertEqual(self.visit.updated_by, self.owner)
        self.assertEqual(self.visit.current_status, VisitInstance.Status.SCHEDULED)

    def test_invalid_post_is_422_and_targets_the_modal(self):
        """An unreadable date re-renders the modal with 422."""
        response = self.htmx_post(
            self.url("visit_update", self.visit.pk), {"due_date": "demain"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.visit.refresh_from_db()
        self.assertIsNone(self.visit.due_date)

    def test_answers_are_not_editable_through_the_planning_form(self):
        """Extra posted fields (answers, status, schema) are ignored."""
        self.htmx_post(
            self.url("visit_update", self.visit.pk),
            {
                "due_date": "2031-01-02",
                "current_status": "VALIDATED",
                "data": '{"answers": {"f_mesure": 5}}',
                "instance_schema": "{}",
            },
        )
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.current_status, VisitInstance.Status.SCHEDULED)
        self.assertEqual(self.visit.answers, {})
        self.assertEqual(self.visit.instance_schema, SAMPLE_SCHEMA)
