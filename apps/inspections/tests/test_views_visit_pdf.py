"""Tests for the blank PDF export of a visit (visit_pdf service and view)."""

from core.tests.helpers import HtmxClientMixin
from django.test import TestCase
from django.urls import reverse

from inspections.services.visit_pdf import build_blank_questionnaire_context
from inspections.tests.factories import VisitInstanceFactory


class VisitExportPdfTests(HtmxClientMixin, TestCase):
    """Export of the blank questionnaire of a visit."""

    def setUp(self):
        """Create a visit of the logged-in owner."""
        super().setUp()
        self.visit = VisitInstanceFactory(
            created_by=self.owner, folder__created_by=self.owner
        )
        self.url = reverse("inspections:visit_export_pdf", args=[self.visit.pk])

    def test_owner_downloads_a_pdf(self):
        """The owner gets a PDF attachment named after the folder reference."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(self.visit.folder.reference, response["Content-Disposition"])

    def test_other_user_gets_404(self):
        """A user who does not own the folder gets a 404."""
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_anonymous_htmx_request_gets_401(self):
        """An anonymous HTMX request gets 401 with an HX-Redirect header."""
        self.client.logout()
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        self.assertIn("HX-Redirect", response)

    def test_archived_visit_can_be_exported(self):
        """An archived visit can still be exported."""
        self.visit.archive(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_context_lists_all_fields_in_order_without_answers(self):
        """The context follows the snapshot order and ignores the answers."""
        self.visit.data = {"answers": {"f_observation": "secret"}}
        self.visit.save()
        context = build_blank_questionnaire_context(self.visit)
        expected = [
            f["id"]
            for s in sorted(
                self.visit.instance_schema["sections"], key=lambda s: s["order"]
            )
            for f in sorted(s["fields"], key=lambda f: f["order"])
        ]
        got = [f["id"] for s in context["sections"] for f in s["fields"]]
        self.assertEqual(got, expected)
        self.assertNotIn("answers", context)
