"""Tests of the client address: Sirene import and refresh, certification and map."""

from datetime import date
from unittest import mock

from core.tests.helpers import GEOCODING_GET, geo_router, make_certified
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.models import Company
from crm.services.company import apply_sirene_changes, get_sirene_changes
from crm.tests.factories import CompanyFactory
from crm.tests.helpers import (
    SIRET_SIEGE,
    fake_response,
    load_fixture,
    sirene_router,
)
from crm.tests.test_views import CrmViewTestCase, company_post


def both_networks(sirene_routes, **geo):
    """Build a ``requests.get`` replacement for Sirene, NAF and the geocoder.

    Args:
        sirene_routes: Mapping ``{siret: fixture file name}``.
        **geo: Passed to ``geo_router``.

    Returns:
        The mock, recording every call.
    """
    sirene = sirene_router(
        {
            siret: fake_response(200, load_fixture(f))
            for siret, f in sirene_routes.items()
        }
    )
    geocoder = geo_router(**geo)

    def fake_get(url, *args, **kwargs):
        """Route the call to the geocoder or to Sirene."""
        target = geocoder if "geocodage.test" in url else sirene
        return target(url, *args, **kwargs)

    return mock.Mock(side_effect=fake_get)


@override_settings(GEOCODING_ENABLED=True)
class CreateCompanyAddressTests(CrmViewTestCase):
    """Creating a client certifies its address and records where it comes from."""

    url = reverse("crm:create_company")

    def post(self, **overrides):
        """Create a client with the fake networks installed.

        Args:
            **overrides: Overrides of the posted data.

        Returns:
            The created company.
        """
        router = both_networks({SIRET_SIEGE: "etab_siege_actif.json"})
        patcher = mock.patch(GEOCODING_GET, new=router)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.htmx_post(self.url, company_post(**overrides))
        return Company.objects.get()

    def test_address_is_certified_on_creation(self):
        """The posted address is geocoded server side."""
        company = self.post()
        self.assertTrue(company.address_certified)
        self.assertTrue(company.has_coordinates)

    def test_coordinates_in_the_form_are_ignored(self):
        """Coordinates cannot be posted: they are computed from the address."""
        company = self.post(latitude="1", longitude="2", address_certified="on")
        self.assertAlmostEqual(float(company.latitude), 48.869141, places=5)

    def test_address_from_sirene_is_flagged(self):
        """An address left as Sirene gave it has the Sirene origin and its INSEE code."""
        company = self.post()
        self.assertEqual(company.address_source, Company.AddressSource.SIRENE)

    def test_edited_address_stays_manual(self):
        """An address changed after the SIRET search is a typed one."""
        company = self.post(address_line="1 RUE AUTRE")
        self.assertEqual(company.address_source, Company.AddressSource.MANUAL)

    def test_creation_works_when_the_geocoder_is_down(self):
        """A geocoder failure does not prevent the creation: the address is uncertified."""
        router = both_networks(
            {SIRET_SIEGE: "etab_siege_actif.json"},
            search=fake_response(503, {}),
        )
        patcher = mock.patch(GEOCODING_GET, new=router)
        patcher.start()
        self.addCleanup(patcher.stop)
        response = self.htmx_post(self.url, company_post())
        self.assertEqual(response.status_code, 200)
        company = Company.objects.get()
        self.assertFalse(company.address_certified)
        self.assertIsNone(company.latitude)

    def test_address_parts_are_required(self):
        """Street, postal code and city are mandatory, as the single address was."""
        response = self.htmx_post(self.url, company_post(city=""))
        self.assertEqual(response.status_code, 422)
        self.assertIn("city", response.context["form"].errors)


@override_settings(GEOCODING_ENABLED=True)
class SireneAddressRefreshTests(TestCase):
    """The Sirene refresh proposes the address as one line and certifies it again."""

    def setUp(self):
        """Create a certified client with an old address."""
        super().setUp()
        cache.clear()
        from accounts.tests.factories import UserFactory

        from crm.services.company import INSEEApiClient

        self.user = UserFactory()
        router = both_networks({SIRET_SIEGE: "etab_siege_actif.json"})
        patcher = mock.patch(GEOCODING_GET, new=router)
        self.router = patcher.start()
        self.addCleanup(patcher.stop)
        self.data = INSEEApiClient.fetch_by_siret(SIRET_SIEGE)
        self.company = make_certified(
            CompanyFactory(
                siret=SIRET_SIEGE,
                address_line="Ancienne adresse",
                postal_code="69001",
                city="LYON",
                creation_date=date(2000, 1, 1),
            ),
            "45.76",
            "4.83",
        )

    def test_address_is_one_change_with_both_values(self):
        """The modal shows one « Adresse » line, current and new."""
        change = next(
            c
            for c in get_sirene_changes(self.company, self.data)
            if c["field"] == "address"
        )
        self.assertEqual(change["label"], "Adresse")
        self.assertEqual(change["current"], "Ancienne adresse, 69001 LYON")
        self.assertEqual(change["new"], "10 RUE DE LA PAIX, 75002 PARIS")

    def test_accepting_it_writes_the_parts_and_certifies_again(self):
        """The three parts are written, the INSEE code kept and the position recomputed."""
        self.assertEqual(
            apply_sirene_changes(self.company, self.user, self.data, ["address"]),
            ["address"],
        )
        company = Company.objects.get(pk=self.company.pk)
        self.assertEqual(
            (company.address_line, company.postal_code, company.city),
            ("10 RUE DE LA PAIX", "75002", "PARIS"),
        )
        self.assertEqual(company.address_source, Company.AddressSource.SIRENE)
        self.assertTrue(company.address_certified)
        self.assertAlmostEqual(float(company.latitude), 48.869141, places=5)

    def test_geocoder_down_leaves_the_new_address_uncertified(self):
        """The address is updated even if it cannot be located now."""
        with mock.patch(
            GEOCODING_GET, new=both_networks({}, search=fake_response(503, {}))
        ):
            apply_sirene_changes(self.company, self.user, self.data, ["address"])
        company = Company.objects.get(pk=self.company.pk)
        self.assertEqual(company.city, "PARIS")
        self.assertFalse(company.address_certified)
        self.assertIsNone(company.latitude)

    def test_unchanged_address_is_not_proposed_and_keeps_its_position(self):
        """Same address: no change listed and the stored coordinates are kept."""
        company = make_certified(
            CompanyFactory(
                address_line=self.data["address_line"],
                postal_code=self.data["postal_code"],
                city=self.data["city"],
            ),
            "1.5",
            "2.5",
        )
        self.assertNotIn(
            "address", [c["field"] for c in get_sirene_changes(company, self.data)]
        )
        self.assertEqual(
            apply_sirene_changes(company, self.user, self.data, ["address"]), []
        )
        company.refresh_from_db()
        self.assertEqual(float(company.latitude), 1.5)

    def test_empty_sirene_address_never_blanks_the_client(self):
        """A Sirene answer without street or city proposes nothing."""
        self.data.update(address_line="", city="")
        self.assertNotIn(
            "address", [c["field"] for c in get_sirene_changes(self.company, self.data)]
        )


class CompanyPageAddressTests(CrmViewTestCase):
    """The client page shows the address, its badge and the map."""

    def test_certified_address_shows_the_badge_and_the_map(self):
        """A certified client has a map with its coordinates."""
        company = make_certified(CompanyFactory(created_by=self.owner))
        response = self.client.get(reverse("crm:company_detail", args=[company.pk]))
        self.assertContains(response, "Adresse certifiée")
        self.assertContains(response, "data-address-map")
        self.assertContains(response, 'data-lat="48.869141"')

    def test_uncertified_address_is_to_check_and_has_no_map(self):
        """Without coordinates the badge asks for a check and no map is drawn."""
        company = CompanyFactory(created_by=self.owner)
        response = self.client.get(reverse("crm:company_detail", args=[company.pk]))
        self.assertContains(response, "Adresse à vérifier")
        self.assertNotContains(response, "data-address-map")
