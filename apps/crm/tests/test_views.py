"""Tests for the client and contact views (crm/views.py).

The network is patched (see ``crm/tests/helpers.py``): the Sirene API and the NAF
service are never reached.
"""

from datetime import date
from unittest import mock

from core.tests.helpers import HtmxClientMixin
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from crm.models import Company, Contact
from crm.tests.factories import CompanyFactory, ContactFactory
from crm.tests.helpers import (
    GET_COMPANY,
    SIRET_SECONDAIRE,
    SIRET_SIEGE,
    fake_response,
    load_fixture,
    sirene_router,
    sirene_urls,
)

COMPANY_GRID = "crm/partials/company/company_grid.html"
COMPANY_MODAL = "crm/partials/company/company_form_modal.html"
CONTACT_GRID = "crm/partials/contact/contact_grid.html"
CONTACT_MODAL = "crm/partials/contact/contact_form_modal.html"


def company_post(**overrides):
    """Build valid POST data for the company form.

    Args:
        **overrides: Values replacing the defaults.

    Returns:
        The data to post.
    """
    data = {
        "name": "ACME INDUSTRIES",
        "siren": "123456782",
        "siret": SIRET_SIEGE,
        "business_line": "62.01Z",
        "company_size_category": "PME",
        "creation_date": "2010-01-01",
        "address": "10 RUE DE LA PAIX, 75002 PARIS",
    }
    data.update(overrides)
    return data


class CrmViewTestCase(HtmxClientMixin, TestCase):
    """Base class: clear the cache and patch the network with a head office fixture."""

    def setUp(self):
        """Clear the cache and install the fake network for the whole test."""
        super().setUp()
        cache.clear()

    def network(self, **routes):
        """Patch ``requests.get`` with a fake Sirene API.

        Args:
            **routes: Mapping ``{siret: fixture file name}`` served with a 200.

        Returns:
            The fake network.
        """
        responses = {
            siret: fake_response(200, load_fixture(f)) for siret, f in routes.items()
        }
        router = sirene_router(responses)
        patcher = mock.patch(GET_COMPANY, new=router)
        patcher.start()
        self.addCleanup(patcher.stop)
        return router


class CreateCompanyTests(CrmViewTestCase):
    """``create_company`` modal."""

    url = reverse("crm:create_company")

    def test_get_renders_the_modal_with_a_read_only_reference(self):
        """The modal is empty and the reference field is disabled."""
        response = self.htmx_get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, COMPANY_MODAL)
        self.assertTrue(response.context["form"].fields["reference"].disabled)

    def test_invalid_post_is_422_with_the_modal(self):
        """A missing name re-renders the modal with 422 and creates nothing."""
        response = self.htmx_post(self.url, company_post(name=""))
        self.assertEqual(response.status_code, 422)
        self.assertTemplateUsed(response, COMPANY_MODAL)
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(Company.objects.count(), 0)

    def test_duplicate_siret_is_refused(self):
        """The SIRET is unique: a second client with the same one gives 422."""
        CompanyFactory(siret=SIRET_SIEGE)
        self.network()
        response = self.htmx_post(self.url, company_post())
        self.assertEqual(response.status_code, 422)
        self.assertIn("siret", response.context["form"].errors)

    def test_valid_post_returns_the_grid_and_closes_the_modal(self):
        """A valid POST creates the client for the user and returns the grid."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        response = self.htmx_post(self.url, company_post())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, COMPANY_GRID)
        self.assertEqual(response["HX-Trigger"], "closeModal")
        company = Company.objects.get()
        self.assertEqual(
            (company.created_by, company.name), (self.owner, "ACME INDUSTRIES")
        )
        self.assertEqual(company.creation_date, date(2010, 1, 1))

    def test_reference_is_generated_and_cannot_be_posted(self):
        """A reference posted by the form is ignored, the generated one is stored."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        self.htmx_post(self.url, company_post(reference="SOC-PIRATE"))
        company = Company.objects.get()
        self.assertRegex(company.reference, r"^SOC-\d{4}-0001$")

    def test_sirene_status_is_read_from_the_api_after_creation(self):
        """The state, head office and NAF activity come from the API, not from the form."""
        router = self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        self.htmx_post(
            self.url,
            company_post(
                administrative_state="C",
                headquarters_address="piraté",
                activity_naf25="00.00Z",
            ),
        )
        company = Company.objects.get()
        self.assertEqual(company.administrative_state, "A")
        self.assertEqual(company.headquarters_siret, SIRET_SIEGE)
        self.assertEqual(company.headquarters_address, "10 RUE DE LA PAIX, 75002 PARIS")
        self.assertEqual(company.activity_naf25, "62.01Z")
        self.assertEqual(company.activity_naf25_label, "Programmation informatique")
        self.assertEqual(len(sirene_urls(router)), 1)

    def test_creation_still_works_when_sirene_is_down(self):
        """If the API cannot be reached the client is created without Sirene data."""
        self.network()
        response = self.htmx_post(self.url, company_post())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Company.objects.get().administrative_state, "")

    def test_the_search_answer_is_reused_by_the_creation(self):
        """The SIRET search and the creation ask the API only once."""
        router = self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        self.htmx_get(reverse("crm:search_siret_api"), {"siret_search": SIRET_SIEGE})
        self.htmx_post(self.url, company_post())
        self.assertEqual(len(sirene_urls(router)), 1)

    def test_optional_fields_may_be_empty(self):
        """The number of employees, VAT number and website are optional."""
        self.network()
        response = self.htmx_post(
            self.url, company_post(nb_employees="", vat_number="", website="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Company.objects.get().nb_employees)


class SearchSiretTests(CrmViewTestCase):
    """``search_siret_api``: the creation form auto-completion."""

    url = reverse("crm:search_siret_api")

    def test_short_or_invalid_siret_gives_an_empty_answer(self):
        """A value that is not 14 digits makes no request."""
        router = self.network()
        for value in ("", "123", "1234567820001X", "1" * 15):
            with self.subTest(value=value):
                response = self.htmx_get(self.url, {"siret_search": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"")
        self.assertEqual(router.call_count, 0)

    def test_found_siret_injects_the_data(self):
        """The fragment confirms the company and fills the form fields."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        response = self.htmx_get(self.url, {"siret_search": SIRET_SIEGE})
        self.assertTrue(response.context["found"])
        self.assertContains(response, "ACME INDUSTRIES")
        self.assertContains(response, "Programmation informatique (62.01Z)")
        self.assertContains(response, "siège social")
        self.assertIsNone(response.context["alert"])
        self.assertEqual(
            response.context["legal_structure_label"],
            "SAS, société par actions simplifiée",
        )

    def test_spaces_and_dashes_are_ignored(self):
        """A SIRET typed with spaces or dashes is cleaned."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        response = self.htmx_get(self.url, {"siret_search": "123 456 782-00010"})
        self.assertTrue(response.context["found"])

    def test_closed_establishment_shows_an_alert(self):
        """A closed establishment adds the cessation alert."""
        self.network(
            **{
                SIRET_SECONDAIRE: "etab_ferme.json",
                SIRET_SIEGE: "etab_siege_actif.json",
            }
        )
        response = self.htmx_get(self.url, {"siret_search": SIRET_SECONDAIRE})
        self.assertEqual(response.context["alert"]["kind"], "closed")
        self.assertEqual(response.context["alert"]["since"], date(2023, 3, 1))

    def test_unknown_siret(self):
        """An unknown SIRET says nothing was found."""
        self.network()
        response = self.htmx_get(self.url, {"siret_search": SIRET_SIEGE})
        self.assertFalse(response.context["found"])
        self.assertEqual(response.context["query"], SIRET_SIEGE)

    def test_post_is_refused(self):
        """The search is GET only."""
        self.assertEqual(self.client.post(self.url).status_code, 405)


class SireneRefreshTests(CrmViewTestCase):
    """``company_sirene_refresh``: comparison (GET) and application (POST)."""

    def setUp(self):
        """Create a client that differs from the Sirene head office fixture."""
        super().setUp()
        self.company = CompanyFactory(
            created_by=self.owner,
            siret=SIRET_SIEGE,
            siren="123456782",
            name="Ancien nom",
            address="Ancienne adresse",
            website="https://client.example",
        )
        self.url = reverse("crm:company_sirene_refresh", args=[self.company.pk])

    def test_get_lists_the_differences(self):
        """The comparison modal lists the changed fields with both values."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        response = self.htmx_get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "crm/partials/company/company_sirene_modal.html"
        )
        fields = {c["field"] for c in response.context["changes"]}
        self.assertIn("name", fields)
        self.assertIn("address", fields)
        self.assertNotIn("website", fields)
        self.assertNotIn("siret", fields)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Ancien nom")

    def test_get_always_asks_the_api_again(self):
        """The refresh never reuses a cached answer."""
        router = self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        self.htmx_get(self.url)
        self.htmx_get(self.url)
        self.assertEqual(len(sirene_urls(router)), 2)

    def test_post_applies_only_the_ticked_fields_and_refreshes(self):
        """The ticked fields are applied with fresh data, the others are kept."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        response = self.htmx_post(self.url, {"fields": ["name"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "ACME INDUSTRIES")
        self.assertEqual(self.company.address, "Ancienne adresse")
        self.assertEqual(self.company.updated_by, self.owner)

    def test_post_ignores_values_and_fields_sent_by_the_form(self):
        """Values posted by the client are never used, protected fields never written."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        self.htmx_post(
            self.url,
            {
                "fields": ["name", "website", "siret"],
                "name": "Piraté",
                "website": "https://evil.example",
            },
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "ACME INDUSTRIES")
        self.assertEqual(self.company.website, "https://client.example")
        self.assertEqual(self.company.siret, SIRET_SIEGE)

    def test_post_with_nothing_ticked_changes_nothing(self):
        """An empty selection refreshes the page without writing."""
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        response = self.htmx_post(self.url, {})
        self.assertEqual(response["HX-Refresh"], "true")
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Ancien nom")

    def test_silent_api_shows_an_error(self):
        """If Sirene gives nothing: 200 on GET, 422 on POST, with the message."""
        self.network()
        response = self.htmx_get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Aucune donnée récupérée", response.context["error"])
        response = self.htmx_post(self.url, {"fields": ["name"]})
        self.assertEqual(response.status_code, 422)

    def test_archived_client_is_409(self):
        """An archived client cannot be refreshed."""
        self.company.archive(self.owner)
        self.network(**{SIRET_SIEGE: "etab_siege_actif.json"})
        self.assertEqual(self.htmx_get(self.url).status_code, 409)
        self.assertEqual(
            self.htmx_post(self.url, {"fields": ["name"]}).status_code, 409
        )

    def test_unreadable_date_gives_422_with_the_differences(self):
        """A value that cannot be stored re-renders the modal with 422."""
        payload = load_fixture("etab_siege_actif.json")
        payload["etablissement"]["dateCreationEtablissement"] = "pas une date"
        self.company.creation_date = date(1999, 1, 1)
        self.company.save()
        router = sirene_router({SIRET_SIEGE: fake_response(200, payload)})
        with mock.patch(GET_COMPANY, new=router):
            response = self.htmx_post(self.url, {"fields": ["creation_date"]})
        self.assertEqual(response.status_code, 422)
        self.assertIn("date illisible", response.context["error"])


class CompanyInlineTests(CrmViewTestCase):
    """``company_inline_update`` and ``company_inline_read``."""

    def setUp(self):
        """Create a client."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner)
        self.url = reverse("crm:company_inline_update", args=[self.company.pk])

    def test_get_form_and_read(self):
        """GET renders the pre-filled form, the read view renders the client."""
        response = self.htmx_get(self.url)
        self.assertTemplateUsed(response, "crm/partials/company/company_update.html")
        self.assertEqual(response.context["form"].instance, self.company)
        response = self.htmx_get(
            reverse("crm:company_inline_read", args=[self.company.pk])
        )
        self.assertContains(response, self.company.name)

    def test_valid_post_updates_and_returns_the_read_fragment(self):
        """A valid POST saves the client and returns the read fragment."""
        data = company_post(siret=self.company.siret, name="Nouveau nom")
        response = self.htmx_post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "crm/partials/company/company_read.html")
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Nouveau nom")
        self.assertEqual(self.company.updated_by, self.owner)

    def test_reference_cannot_be_changed(self):
        """The posted reference is ignored."""
        reference = self.company.reference
        self.htmx_post(
            self.url, company_post(siret=self.company.siret, reference="SOC-X")
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.reference, reference)

    def test_invalid_post_re_renders_the_form(self):
        """A missing name gives the form back (status 200) with its errors."""
        response = self.htmx_post(
            self.url, company_post(siret=self.company.siret, name="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "crm/partials/company/company_update.html")
        self.assertIn("name", response.context["form"].errors)
        self.company.refresh_from_db()
        self.assertNotEqual(self.company.name, "")


class CreateContactTests(CrmViewTestCase):
    """``create_contact`` modal and ``contact_inline_update``."""

    url = reverse("crm:create_contact")

    def setUp(self):
        """Create the client the contacts belong to."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner)

    def data(self, **overrides):
        """Build valid POST data for a contact.

        Args:
            **overrides: Values replacing the defaults.

        Returns:
            The data to post.
        """
        data = {
            "company": self.company.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "position": "Directrice",
        }
        data.update(overrides)
        return data

    def test_get_preselects_the_company(self):
        """``?company=`` pre-fills the client."""
        response = self.htmx_get(self.url, {"company": self.company.pk})
        self.assertTemplateUsed(response, CONTACT_MODAL)
        self.assertEqual(
            str(response.context["form"].initial["company"]), str(self.company.pk)
        )

    def test_get_without_company(self):
        """Without parameter the modal is empty."""
        response = self.htmx_get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial, {})

    def test_invalid_post_is_422(self):
        """A missing last name re-renders the modal with 422."""
        response = self.htmx_post(self.url, self.data(last_name=""))
        self.assertEqual(response.status_code, 422)
        self.assertTemplateUsed(response, CONTACT_MODAL)
        self.assertEqual(Contact.objects.count(), 0)

    def test_invalid_email_is_refused(self):
        """A malformed email is refused."""
        response = self.htmx_post(self.url, self.data(email="pas-un-email"))
        self.assertEqual(response.status_code, 422)
        self.assertIn("email", response.context["form"].errors)

    def test_valid_post_creates_the_contact(self):
        """A valid POST creates the contact for the user and refreshes the page."""
        response = self.htmx_post(self.url, self.data())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Refresh"], "true")
        contact = Contact.objects.get()
        self.assertEqual(
            (contact.created_by, contact.company), (self.owner, self.company)
        )

    def test_inline_update(self):
        """Editing a contact saves it and returns the read fragment, errors give the form."""
        contact = ContactFactory(company=self.company)
        url = reverse("crm:contact_inline_update", args=[contact.pk])
        self.assertTemplateUsed(
            self.htmx_get(url), "crm/partials/contact/contact_update.html"
        )
        response = self.htmx_post(url, self.data(first_name="Grace"))
        self.assertTemplateUsed(response, "crm/partials/contact/contact_read.html")
        contact.refresh_from_db()
        self.assertEqual(
            (contact.first_name, contact.updated_by), ("Grace", self.owner)
        )
        response = self.htmx_post(url, self.data(first_name=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["form"].errors)
        response = self.htmx_get(reverse("crm:contact_inline_read", args=[contact.pk]))
        self.assertContains(response, "Directrice")


class CompanyListTests(CrmViewTestCase):
    """``company_list`` and ``company_list_paginated``."""

    def setUp(self):
        """Create 16 active clients and an archived one."""
        super().setUp()
        self.companies = [CompanyFactory(created_by=self.owner) for _ in range(16)]
        self.archived = CompanyFactory(created_by=self.owner, archived=True)
        self.list_url = reverse("crm:company_list")

    def test_full_page_shows_fifteen_active_clients(self):
        """By default the page lists 15 active clients, with a second page."""
        response = self.client.get(self.list_url)
        self.assertTemplateUsed(response, "crm/company.html")
        self.assertEqual(len(response.context["companies"]), 15)
        self.assertEqual(response.context["page_obj"].paginator.count, 16)
        self.assertNotIn(self.archived, response.context["companies"])

    def test_paginated_returns_only_the_grid(self):
        """The paginated view returns the grid partial; page 2 holds the last client."""
        response = self.htmx_get(reverse("crm:company_list_paginated", args=[2]))
        self.assertTemplateUsed(response, COMPANY_GRID)
        self.assertTemplateNotUsed(response, "crm/company.html")
        self.assertEqual(len(response.context["companies"]), 1)

    def test_status_filter_in_both_views(self):
        """``status=archived`` lists only the archived client, in both views."""
        grid_url = reverse("crm:company_list_paginated", args=[1])
        for response in (
            self.client.get(self.list_url, {"status": "archived"}),
            self.htmx_get(grid_url, {"status": "archived"}),
        ):
            self.assertEqual(list(response.context["companies"]), [self.archived])

    def test_search_in_both_views(self):
        """The search matches on the name in both views."""
        target = self.companies[3]
        grid_url = reverse("crm:company_list_paginated", args=[1])
        for response in (
            self.client.get(self.list_url, {"q": target.siret}),
            self.htmx_get(grid_url, {"q": target.siret}),
        ):
            self.assertEqual(list(response.context["companies"]), [target])

    def test_sort_outside_the_whitelist_is_ignored(self):
        """An unknown sort falls back to the name order."""
        response = self.client.get(self.list_url, {"sort": "created_by__password"})
        self.assertEqual(response.status_code, 200)
        names = [c.name for c in response.context["companies"]]
        self.assertEqual(names, sorted(names))

    def test_allowed_sort(self):
        """``-created_at`` puts the newest client first."""
        response = self.client.get(self.list_url, {"sort": "-created_at"})
        self.assertEqual(response.context["companies"][0], self.companies[-1])


class ContactListTests(CrmViewTestCase):
    """``contact_list`` and ``contact_list_paginated``."""

    def setUp(self):
        """Create 16 active contacts of one client and an archived one."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner)
        self.contacts = [ContactFactory(company=self.company) for _ in range(16)]
        self.archived = ContactFactory(company=self.company, archived=True)
        self.list_url = reverse("crm:contact_list")

    def test_full_page_shows_fifteen_active_contacts(self):
        """By default the page lists 15 active contacts and offers the client filter."""
        response = self.client.get(self.list_url)
        self.assertTemplateUsed(response, "crm/contact.html")
        self.assertEqual(len(response.context["contacts"]), 15)
        self.assertEqual(response.context["page_obj"].paginator.count, 16)
        self.assertIn(self.company, response.context["companies"])

    def test_paginated_returns_only_the_grid(self):
        """The paginated view returns the grid partial."""
        response = self.htmx_get(reverse("crm:contact_list_paginated", args=[2]))
        self.assertTemplateUsed(response, CONTACT_GRID)
        self.assertEqual(len(response.context["contacts"]), 1)

    def test_pagination_links_point_to_the_other_page(self):
        """The grid links to the previous and next pages (regression: 500 above 15 contacts)."""
        first = self.htmx_get(reverse("crm:contact_list_paginated", args=[1]))
        self.assertContains(first, reverse("crm:contact_list_paginated", args=[2]))
        second = self.htmx_get(reverse("crm:contact_list_paginated", args=[2]))
        self.assertContains(second, reverse("crm:contact_list_paginated", args=[1]))

    def test_status_filter_values(self):
        """``archived`` lists the archived contact, ``all`` lists everybody."""
        response = self.client.get(self.list_url, {"status": "archived"})
        self.assertEqual(list(response.context["contacts"]), [self.archived])
        response = self.client.get(self.list_url, {"status": "all"})
        self.assertEqual(response.context["page_obj"].paginator.count, 17)

    def test_company_filter(self):
        """The client filter keeps the contacts of that client only."""
        other = ContactFactory()
        response = self.client.get(self.list_url, {"company": other.company_id})
        self.assertEqual(list(response.context["contacts"]), [other])
