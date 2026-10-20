"""Isolation tests: a user never reaches the objects of another one.

Every URL that takes the primary key of a folder, visit, recommendation or private
template answers 404 to a logged-in user who does not own the object, in GET and in
POST, and a POST changes nothing in the database. The medias URLs are covered by
``medias/tests/test_isolation.py``.

The ``test_*`` tests describe the isolation planned for sprint 5 (global
search and CRM views are not filtered by user yet): they are marked
``expectedFailure`` and must lose that mark when the isolation is implemented.
"""

from core.tests.helpers import BOTH, GET, POST, HtmxClientMixin, IsolationMixin, Route
from crm.models import Company, Contact
from crm.tests.factories import CompanyFactory, ContactFactory
from django.test import TestCase
from django.urls import reverse

from inspections.models import (
    InspectionFolder,
    Recommandation,
    VisitInstance,
    VisitTemplate,
)
from inspections.tests.factories import (
    InspectionFolderFactory,
    RecommandationFactory,
    VisitInstanceFactory,
    VisitTemplateFactory,
)

FOLDER_ROUTES = [
    Route("inspections:folder_detail", "pk", GET),
    Route("inspections:folder_tab_overview", "pk", GET),
    Route("inspections:folder_tab_visit", "pk", GET),
    Route("inspections:folder_tab_recommandations", "pk", GET),
    Route("inspections:folder_inline_update", "pk", BOTH),
    Route("inspections:folder_inline_read", "pk", GET),
    Route("inspections:folder_archive", "folder_id", BOTH),
    Route("inspections:folder_unarchive", "folder_id", POST),
    Route("inspections:folder_delete", "folder_id", BOTH),
    Route("inspections:visit_create", "folder_id", BOTH),
]
VISIT_ROUTES = [
    Route("inspections:visit_update", "pk", BOTH),
    Route("inspections:visit_toggle_done", "pk", POST),
    Route("inspections:visit_archive", "pk", POST),
    Route("inspections:visit_unarchive", "pk", POST),
    Route("inspections:visit_delete", "pk", BOTH),
    Route("inspections:visit_form", "pk", GET),
    Route("inspections:visit_save_answers", "pk", POST),
    Route("inspections:visit_complete", "pk", POST),
    Route("inspections:visit_reopen", "pk", POST),
]
RECOMMANDATION_ROUTES = [
    Route("inspections:recommandation_inline_update", "pk", BOTH),
    Route("inspections:recommandation_inline_read", "pk", GET),
    Route("inspections:recommandation_archive", "pk", POST),
    Route("inspections:recommandation_unarchive", "pk", POST),
    Route("inspections:recommandation_delete", "pk", BOTH),
]
TEMPLATE_ROUTES = [
    Route("inspections:template_edit", "pk", BOTH),
    Route("inspections:template_read", "pk", GET),
    Route("inspections:template_duplicate", "pk", POST),
    Route("inspections:template_toggle_share", "pk", POST),
    Route("inspections:template_archive", "pk", BOTH),
    Route("inspections:template_unarchive", "pk", POST),
    Route("inspections:template_delete", "pk", BOTH),
]


def database_state():
    """Return a snapshot of the tables holding user data.

    Returns:
        A list with the rows of folders, visits, recommendations and templates.
    """
    models = (InspectionFolder, VisitInstance, Recommandation, VisitTemplate)
    return [list(model.objects.order_by("pk").values()) for model in models]


class IsolationTests(IsolationMixin, HtmxClientMixin, TestCase):
    """Objects of ``owner`` are invisible to ``other``.

    Data: a folder with a visit and a recommendation, and a private template, all
    created by ``owner``.
    """

    def setUp(self):
        """Create the objects of the owner and log ``other`` in."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner)
        self.folder = InspectionFolderFactory(
            company=self.company, created_by=self.owner
        )
        kwargs = {"folder": self.folder, "created_by": self.owner}
        self.visit = VisitInstanceFactory(**kwargs)
        self.recommandation = RecommandationFactory(**kwargs)
        self.template = VisitTemplateFactory(created_by=self.owner)
        self.client.force_login(self.other)

    def database_state(self):
        """Return a snapshot of the tables the routes could change.

        Returns:
            The rows of folders, visits, recommendations and templates.
        """
        return database_state()

    def test_folder_urls_return_404_to_another_user(self):
        """All the folder URLs answer 404 to a user who does not own the folder."""
        self.check_routes_404(FOLDER_ROUTES, self.folder)

    def test_visit_urls_return_404_to_another_user(self):
        """All the visit URLs answer 404 to a user who does not own the folder."""
        self.check_routes_404(VISIT_ROUTES, self.visit)
        url = reverse(
            "inspections:visit_form_section", args=[self.visit.pk, "s_general"]
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_recommandation_urls_return_404_to_another_user(self):
        """All the recommendation URLs answer 404 to a user who does not own the folder."""
        self.check_routes_404(RECOMMANDATION_ROUTES, self.recommandation)

    def test_private_template_urls_return_404_to_another_user(self):
        """Reading, editing or sharing someone else's private template gives 404."""
        self.check_routes_404(TEMPLATE_ROUTES, self.template)

    def test_owner_still_reaches_everything(self):
        """Control: the same URLs work for the owner (nothing is 404 by accident)."""
        self.client.force_login(self.owner)
        for name, obj in (
            ("inspections:folder_detail", self.folder),
            ("inspections:visit_form", self.visit),
            ("inspections:recommandation_inline_read", self.recommandation),
            ("inspections:template_read", self.template),
        ):
            with self.subTest(url=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=[obj.pk])).status_code, 200
                )

    def test_visit_of_another_user_is_not_modified_by_save_answers(self):
        """A foreign POST on ``visit_save_answers`` cannot write answers."""
        url = reverse("inspections:visit_save_answers", args=[self.visit.pk])
        response = self.htmx_post(url, {"field_id": "f_mesure", "value": "5"})
        self.assertEqual(response.status_code, 404)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.answers, {})
        self.assertEqual(self.visit.revision, 0)

    def test_lists_only_show_the_user_folders(self):
        """The folder list, its pagination, the dashboard and the company panel are filtered."""
        mine = InspectionFolderFactory(
            created_by=self.other, company=CompanyFactory(created_by=self.other)
        )
        response = self.client.get(reverse("inspections:folder_list"))
        self.assertEqual(list(response.context["folders"]), [mine])
        response = self.client.get(
            reverse("inspections:folder_list_paginated", args=[1])
        )
        self.assertEqual(list(response.context["folders"]), [mine])
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["last_folder"], mine)
        self.assertNotContains(response, self.folder.reference)

    def test_company_folders_panel_of_another_user_is_404(self):
        """The panel of someone else's client answers 404."""
        response = self.client.get(
            reverse("inspections:company_folders_panel", args=[self.company.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_company_folders_panel_lists_only_the_user_folders(self):
        """The panel of my own client only lists the folders I created."""
        mine = InspectionFolderFactory(created_by=self.other)
        response = self.client.get(
            reverse("inspections:company_folders_panel", args=[mine.company_id])
        )
        self.assertEqual(list(response.context["folders"]), [mine])
        self.assertNotContains(response, self.folder.reference)

    def test_folder_list_filters_cannot_reach_other_users_folders(self):
        """Filtering by someone else's company or reference never shows their folders."""
        url = reverse("inspections:folder_list")
        for params in ({"company": self.company.pk}, {"q": self.folder.reference}):
            with self.subTest(params=params):
                response = self.client.get(url, params)
                self.assertEqual(list(response.context["folders"]), [])

    def test_template_list_hides_private_templates_of_others(self):
        """The template panel does not list another user's private template."""
        response = self.client.get(reverse("inspections:template_panel"))
        self.assertNotContains(response, self.template.name)

    def test_shared_template_is_readable_but_not_editable(self):
        """A shared template can be read and copied by others, never changed."""
        shared = VisitTemplateFactory(created_by=self.owner, shared_template=True)
        self.assertEqual(
            self.client.get(
                reverse("inspections:template_read", args=[shared.pk])
            ).status_code,
            200,
        )
        for name in ("template_edit", "template_archive", "template_delete"):
            with self.subTest(url=name):
                response = self.client.get(
                    reverse(f"inspections:{name}", args=[shared.pk])
                )
                self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("inspections:template_toggle_share", args=[shared.pk])
        )
        self.assertEqual(response.status_code, 404)


class CrmIsolationTests(HtmxClientMixin, TestCase):
    """Clients, contacts and global search only show the objects of the logged-in user."""

    def setUp(self):
        """Create a client, a contact and a folder for ``owner``; log ``other`` in."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner, name="Entreprise Secrète")
        self.contact = ContactFactory(company=self.company, last_name="Confidentiel")
        self.folder = InspectionFolderFactory(
            company=self.company, contact=self.contact, created_by=self.owner
        )
        self.client.force_login(self.other)

    def test_company_detail_is_404_for_another_user(self):
        """The detail page of someone else's client answers 404."""
        response = self.client.get(
            reverse("crm:company_detail", args=[self.company.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_contact_detail_is_404_for_another_user(self):
        """The detail page of someone else's contact answers 404."""
        response = self.client.get(
            reverse("crm:contact_detail", args=[self.contact.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_company_list_hides_clients_of_others(self):
        """The client list only shows the clients of the logged-in user."""
        response = self.client.get(reverse("crm:company_list"))
        self.assertNotContains(response, "Entreprise Secrète")

    def test_contact_list_hides_contacts_of_others(self):
        """The contact list only shows the contacts of the logged-in user."""
        response = self.client.get(reverse("crm:contact_list"))
        self.assertNotContains(response, "Confidentiel")

    def test_company_archive_is_404_for_another_user(self):
        """Someone else's client cannot be archived."""
        response = self.client.post(
            reverse("crm:company_archive", args=[self.company.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_global_search_hides_folders_of_others(self):
        """The global search does not return the folders of other users."""
        response = self.client.get(
            reverse("core:global_search"), {"q": self.folder.reference}
        )
        self.assertEqual(list(response.context["folders"]), [])

    def test_global_search_hides_companies_of_others(self):
        """The global search does not return the clients of other users."""
        response = self.client.get(reverse("core:global_search"), {"q": "Secrète"})
        self.assertEqual(list(response.context["companies"]), [])

    def test_global_search_hides_contacts_of_others(self):
        """The global search does not return the contacts of other users."""
        response = self.client.get(reverse("core:global_search"), {"q": "Confidentiel"})
        self.assertEqual(list(response.context["contacts"]), [])

    def test_companies_and_contacts_of_the_owner_are_unchanged_by_reads(self):
        """Control: the reads above do not alter the CRM data."""
        self.client.get(reverse("crm:company_detail", args=[self.company.pk]))
        self.assertTrue(Company.objects.get(pk=self.company.pk).is_active)
        self.assertTrue(Contact.objects.get(pk=self.contact.pk).is_active)

    def test_every_crm_url_of_a_foreign_object_is_404(self):
        """Detail, edit, archive, delete and refresh URLs of a foreign client or contact give 404."""
        for name, obj in (
            ("company_detail", self.company),
            ("company_inline_update", self.company),
            ("company_inline_read", self.company),
            ("company_archive", self.company),
            ("company_unarchive", self.company),
            ("company_delete", self.company),
            ("company_sirene_refresh", self.company),
            ("contact_detail", self.contact),
            ("contact_inline_update", self.contact),
            ("contact_inline_read", self.contact),
            ("contact_archive", self.contact),
            ("contact_unarchive", self.contact),
            ("contact_delete", self.contact),
        ):
            url = reverse(f"crm:{name}", args=[obj.pk])
            for method in ("GET", "POST"):
                with self.subTest(url=name, method=method):
                    response = self.client.generic(method, url)
                    self.assertIn(response.status_code, (404, 405))
        self.assertTrue(Company.objects.get(pk=self.company.pk).is_active)
        self.assertTrue(Contact.objects.get(pk=self.contact.pk).is_active)

    def test_creation_forms_refuse_a_foreign_client(self):
        """A folder or a contact cannot be created on someone else's client."""
        response = self.htmx_post(
            reverse("inspections:create_folder"), {"company": self.company.pk}
        )
        self.assertEqual(response.status_code, 422)
        response = self.htmx_post(
            reverse("crm:create_contact"),
            {
                "company": self.company.pk,
                "first_name": "A",
                "last_name": "B",
                "position": "C",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Contact.objects.filter(first_name="A").count(), 0)

    def test_foreign_clients_are_not_offered_in_forms_or_filters(self):
        """The folder filter and the contact form only offer my own clients."""
        mine = CompanyFactory(created_by=self.other)
        InspectionFolderFactory(company=mine, created_by=self.other)
        response = self.client.get(reverse("inspections:folder_list"))
        self.assertEqual(list(response.context["companies"]), [mine])
        response = self.htmx_get(reverse("crm:create_contact"))
        self.assertEqual(
            list(response.context["form"].fields["company"].queryset), [mine]
        )
