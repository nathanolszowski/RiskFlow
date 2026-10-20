"""Tests for the folder views (inspections/views.py): modals, lists and inline editing."""

from core.tests.helpers import HtmxClientMixin
from crm.tests.factories import CompanyFactory, ContactFactory
from django.test import TestCase
from django.urls import reverse

from inspections.models import InspectionFolder, Recommandation
from inspections.tests.factories import InspectionFolderFactory, RecommandationFactory

GRID = "inspections/partials/folder/folder_grid.html"
MODAL = "inspections/partials/folder/folder_form_modal.html"


class FolderViewTestCase(HtmxClientMixin, TestCase):
    """Base class: a client with two contacts, owned by the logged-in ``owner``."""

    def setUp(self):
        """Create the client and its contacts."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner)
        self.contact = ContactFactory(company=self.company)
        self.other_contact = ContactFactory(company=self.company)
        self.foreign_contact = ContactFactory()

    def make_folder(self, **kwargs):
        """Create a folder of the owner for the base client.

        Args:
            **kwargs: Overrides passed to ``InspectionFolderFactory``.

        Returns:
            The folder.
        """
        kwargs.setdefault("company", self.company)
        kwargs.setdefault("contact", self.contact)
        kwargs.setdefault("created_by", self.owner)
        return InspectionFolderFactory(**kwargs)


class CreateFolderTests(FolderViewTestCase):
    """``create_folder`` modal and ``folder_contact_field``."""

    url = reverse("inspections:create_folder")

    def test_get_renders_the_modal_without_phase_field(self):
        """The creation modal has no phase field and no contact until a client is chosen."""
        response = self.htmx_get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, MODAL)
        form = response.context["form"]
        self.assertNotIn("current_phase", form.fields)
        self.assertEqual(list(form.fields["contact"].queryset), [])
        self.assertEqual(
            form.fields["contact"].empty_label, "Sélectionnez d'abord un client"
        )

    def test_get_from_a_company_limits_the_contacts(self):
        """With ``?company=`` the company is preselected and the contacts are its own."""
        response = self.htmx_get(self.url, {"company": self.company.pk})
        form = response.context["form"]
        self.assertEqual(form.initial["company"], self.company)
        self.assertEqual(
            set(form.fields["contact"].queryset), {self.contact, self.other_contact}
        )

    def test_invalid_post_is_422_with_the_modal(self):
        """A missing client re-renders the modal with 422 and creates nothing."""
        response = self.htmx_post(self.url, {"inspection_site_address": "x"})
        self.assertEqual(response.status_code, 422)
        self.assertTemplateUsed(response, MODAL)
        self.assertIn("company", response.context["form"].errors)
        self.assertNotIn("HX-Retarget", response)
        self.assertEqual(InspectionFolder.objects.count(), 0)

    def test_valid_post_creates_the_folder_in_preparation(self):
        """A valid POST creates the folder in PREPARATION, owned by the user."""
        response = self.htmx_post(
            self.url,
            {"company": self.company.pk, "contact": self.contact.pk, "notes": "n"},
        )
        self.assertEqual(response.status_code, 204)
        folder = InspectionFolder.objects.get()
        self.assertEqual(folder.current_phase, InspectionFolder.Phase.PREPARATION)
        self.assertEqual(
            (folder.created_by, folder.company, folder.contact),
            (self.owner, self.company, self.contact),
        )
        self.assertRegex(folder.reference, r"^DOS-\d{4}-[0-9A-F]{6}$")

    def test_valid_post_refreshes_the_page(self):
        """The answer is a 204 with ``HX-Refresh``.

        The view returns the grid with ``closeModal`` only when no ``company`` is in the
        request. The form always posts its required ``company`` field, so that branch is
        not reached by the real form, from the list or from a company page.
        """
        response = self.htmx_post(self.url, {"company": self.company.pk})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Refresh"], "true")
        self.assertEqual(InspectionFolder.objects.count(), 1)

    def test_contact_without_company_choice_is_refused(self):
        """A contact cannot be chosen when no client is selected."""
        response = self.htmx_post(self.url, {"contact": self.contact.pk})
        self.assertEqual(response.status_code, 422)

    def test_contact_of_another_client_is_refused(self):
        """A contact of another client is rejected, from the list and from a company page."""
        for extra in ({}, {"company": self.company.pk}):
            with self.subTest(extra=extra):
                response = self.htmx_post(
                    self.url,
                    {
                        "company": self.company.pk,
                        "contact": self.foreign_contact.pk,
                        **extra,
                    },
                )
                self.assertEqual(response.status_code, 422)
                self.assertIn("contact", response.context["form"].errors)
        self.assertEqual(InspectionFolder.objects.count(), 0)

    def test_phase_cannot_be_posted_at_creation(self):
        """A posted phase is ignored: the folder starts in PREPARATION."""
        self.htmx_post(
            self.url, {"company": self.company.pk, "current_phase": "CLOSED"}
        )
        self.assertEqual(InspectionFolder.objects.get().current_phase, "PREPARATION")

    def test_contact_field_lists_only_the_contacts_of_the_client(self):
        """Choosing a client reloads the contact field with its contacts only."""
        url = reverse("inspections:folder_contact_field")
        response = self.htmx_get(url, {"company": self.company.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.context["form"].fields["contact"].queryset),
            {self.contact, self.other_contact},
        )
        self.assertContains(response, self.contact.last_name)
        self.assertNotContains(response, self.foreign_contact.last_name)

    def test_contact_field_without_valid_client_is_empty(self):
        """No client, an unknown client or garbage gives no choice."""
        url = reverse("inspections:folder_contact_field")
        for params in ({}, {"company": "0"}, {"company": "abc"}):
            with self.subTest(params=params):
                response = self.htmx_get(url, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    list(response.context["form"].fields["contact"].queryset), []
                )


class FolderInlineEditTests(FolderViewTestCase):
    """``folder_inline_update`` and ``folder_inline_read``."""

    def setUp(self):
        """Create a folder in PREPARATION."""
        super().setUp()
        self.folder = self.make_folder(current_phase=InspectionFolder.Phase.PREPARATION)
        self.url = reverse("inspections:folder_inline_update", args=[self.folder.pk])

    def test_get_renders_the_form_without_the_creation_phase(self):
        """The edit form does not offer the transient ``Création`` phase."""
        response = self.htmx_get(self.url)
        self.assertTemplateUsed(
            response, "inspections/partials/folder/folder_update.html"
        )
        phases = [
            value
            for value, _ in response.context["form"].fields["current_phase"].choices
        ]
        self.assertNotIn("CREATION", phases)
        self.assertIn("PREPARATION", phases)
        self.assertIn("ARCHIVED", phases)

    def test_creation_phase_is_kept_for_a_folder_still_in_it(self):
        """A folder that is still in ``Création`` keeps that choice."""
        folder = self.make_folder(current_phase=InspectionFolder.Phase.CREATION)
        response = self.htmx_get(
            reverse("inspections:folder_inline_update", args=[folder.pk])
        )
        phases = [
            value
            for value, _ in response.context["form"].fields["current_phase"].choices
        ]
        self.assertIn("CREATION", phases)

    def test_contact_choices_are_limited_to_the_client(self):
        """Only the contacts of the folder's client can be chosen."""
        response = self.htmx_get(self.url)
        queryset = response.context["form"].fields["contact"].queryset
        self.assertEqual(set(queryset), {self.contact, self.other_contact})

    def test_valid_post_returns_the_read_fragment(self):
        """A valid POST saves the folder, records the user and returns the read view."""
        response = self.htmx_post(
            self.url,
            {
                "contact": self.other_contact.pk,
                "current_phase": "VISIT",
                "notes": "nouvelles notes",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "inspections/partials/folder/folder_read.html"
        )
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.current_phase, "VISIT")
        self.assertEqual(self.folder.contact, self.other_contact)
        self.assertEqual(self.folder.updated_by, self.owner)

    def test_invalid_post_re_renders_the_form_with_errors(self):
        """A contact of another client gives the form back (status 200) with its errors."""
        response = self.htmx_post(
            self.url, {"contact": self.foreign_contact.pk, "current_phase": "VISIT"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "inspections/partials/folder/folder_update.html"
        )
        self.assertIn("contact", response.context["form"].errors)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.contact, self.contact)

    def test_company_cannot_be_changed(self):
        """The client is not an editable field."""
        other = CompanyFactory(created_by=self.owner)
        self.htmx_post(self.url, {"company": other.pk, "current_phase": "VISIT"})
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.company, self.company)

    def test_inline_read(self):
        """The read fragment shows the reference of the folder."""
        response = self.htmx_get(
            reverse("inspections:folder_inline_read", args=[self.folder.pk])
        )
        self.assertTemplateUsed(
            response, "inspections/partials/folder/folder_read.html"
        )
        self.assertContains(response, self.folder.reference)


class RecommandationInlineTests(FolderViewTestCase):
    """``recommandation_inline_update`` and ``recommandation_inline_read``."""

    def setUp(self):
        """Create a folder with a recommendation."""
        super().setUp()
        self.folder = self.make_folder()
        self.rec = RecommandationFactory(folder=self.folder, created_by=self.owner)
        self.url = reverse(
            "inspections:recommandation_inline_update", args=[self.rec.pk]
        )

    def test_get_renders_the_form(self):
        """The edit form is pre-filled."""
        response = self.htmx_get(self.url)
        self.assertTemplateUsed(
            response, "inspections/partials/recommandation/recommandation_update.html"
        )
        self.assertEqual(response.context["form"].instance, self.rec)

    def test_valid_post_updates_and_returns_the_read_fragment(self):
        """A valid POST saves the changes and shows the read fragment."""
        response = self.htmx_post(
            self.url,
            {
                "topic": "Électricité",
                "description": "Remplacer le tableau",
                "priority": "HIGH",
                "current_status": "IN_PROGRESS",
                "due_date": "2031-02-03",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "inspections/partials/recommandation/recommandation_read.html"
        )
        self.rec.refresh_from_db()
        self.assertEqual(
            (self.rec.priority, self.rec.current_status), ("HIGH", "IN_PROGRESS")
        )
        self.assertEqual(self.rec.updated_by, self.owner)

    def test_invalid_post_re_renders_the_form(self):
        """A missing description gives the form back with its errors, nothing is saved."""
        response = self.htmx_post(
            self.url, {"topic": "x", "priority": "HIGH", "current_status": "OPEN"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "inspections/partials/recommandation/recommandation_update.html"
        )
        self.assertIn("description", response.context["form"].errors)
        self.rec.refresh_from_db()
        self.assertNotEqual(self.rec.priority, "HIGH")

    def test_unknown_priority_is_refused(self):
        """A value outside the priority choices is refused."""
        response = self.htmx_post(
            self.url,
            {"description": "d", "priority": "URGENT", "current_status": "OPEN"},
        )
        self.assertIn("priority", response.context["form"].errors)

    def test_inline_read(self):
        """The read fragment shows the recommendation."""
        response = self.htmx_get(
            reverse("inspections:recommandation_inline_read", args=[self.rec.pk])
        )
        self.assertContains(response, self.rec.description)

    def test_recommendation_count_is_unchanged_by_edits(self):
        """Editing never creates a second recommendation."""
        self.htmx_post(
            self.url, {"description": "d", "priority": "LOW", "current_status": "OPEN"}
        )
        self.assertEqual(Recommandation.objects.count(), 1)


class FolderListTests(FolderViewTestCase):
    """``folder_list`` and ``folder_list_paginated``."""

    def setUp(self):
        """Create 16 folders of the owner (a client of 15 + 1 on the second page)."""
        super().setUp()
        self.folders = [self.make_folder() for _ in range(16)]
        self.list_url = reverse("inspections:folder_list")

    def test_full_page_shows_the_first_fifteen(self):
        """The page lists 15 folders and knows there is a second page."""
        response = self.client.get(self.list_url)
        self.assertTemplateUsed(response, "inspections/folders.html")
        self.assertEqual(len(response.context["folders"]), 15)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertEqual(
            response.context["phase_choices"], InspectionFolder.Phase.choices
        )

    def test_paginated_returns_only_the_grid(self):
        """The paginated view returns the grid partial: page 2 holds the last folder."""
        response = self.htmx_get(reverse("inspections:folder_list_paginated", args=[2]))
        self.assertTemplateUsed(response, GRID)
        self.assertTemplateNotUsed(response, "inspections/folders.html")
        self.assertEqual(len(response.context["folders"]), 1)

    def test_out_of_range_page_gives_the_last_page(self):
        """A page number beyond the end falls back to the last page."""
        response = self.htmx_get(
            reverse("inspections:folder_list_paginated", args=[99])
        )
        self.assertEqual(response.context["page_obj"].number, 2)

    def test_both_views_apply_the_same_filters(self):
        """Search, status and phase filters give the same result in both views."""
        self.folders[0].archive(self.owner)
        VISIT = InspectionFolder.Phase.VISIT
        InspectionFolder.objects.filter(pk=self.folders[1].pk).update(
            current_phase=VISIT
        )
        cases = [
            ({"status": "archived"}, 1),
            ({"status": "active"}, 15),
            ({"phase": "VISIT"}, 1),
            ({"q": self.folders[2].reference}, 1),
            ({"q": "introuvable"}, 0),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                full = self.client.get(self.list_url, params)
                grid = self.htmx_get(
                    reverse("inspections:folder_list_paginated", args=[1]), params
                )
                self.assertEqual(full.context["page_obj"].paginator.count, expected)
                self.assertEqual(grid.context["page_obj"].paginator.count, expected)

    def test_sort_outside_the_whitelist_is_ignored(self):
        """A sort that is not allowed neither fails nor changes the default order."""
        default = self.client.get(self.list_url).context["folders"]
        response = self.client.get(
            self.list_url, {"sort": "company__created_by__password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["folders"]), list(default))

    def test_allowed_sort_is_applied(self):
        """``sort=reference`` orders by reference."""
        response = self.client.get(self.list_url, {"sort": "reference"})
        references = [f.reference for f in response.context["folders"]]
        self.assertEqual(references, sorted(references))

    def test_company_filter_menu_lists_clients_with_folders(self):
        """The company filter only offers clients that have a folder."""
        CompanyFactory(name="Sans dossier")
        response = self.client.get(self.list_url)
        self.assertEqual(list(response.context["companies"]), [self.company])
