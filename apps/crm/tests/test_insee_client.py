"""Tests for the INSEE Sirene API client (crm/services/company.py::INSEEApiClient).

The network is never reached: ``requests.get`` is patched in both the Sirene client
and the NAF label service, and the answers come from ``crm/tests/fixtures/``.
"""

from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from crm.services.company import INSEEApiClient
from crm.tests.helpers import (
    GET_COMPANY,
    SIRET_SECONDAIRE,
    SIRET_SIEGE,
    fake_response,
    load_fixture,
    naf_urls,
    sirene_router,
    sirene_urls,
)


def ok(name):
    """Build a 200 response holding a fixture.

    Args:
        name: Fixture file name.

    Returns:
        The fake response.
    """
    return fake_response(200, load_fixture(name))


class InseeClientTestCase(SimpleTestCase):
    """Base class: clear the cache before each test and give ``fetch`` helpers."""

    def setUp(self):
        """Clear the cache so that no NAF label is reused between tests."""
        super().setUp()
        cache.clear()

    def fetch(self, routes, siret=SIRET_SIEGE, naf=None):
        """Call ``fetch_by_siret`` with a fake network.

        Args:
            routes: Mapping ``{siret: response}`` served by the fake Sirene API.
            siret: SIRET to look up.
            naf: Response served by the fake NAF service (label fixture by default).

        Returns:
            A tuple ``(data, fake network)``.
        """
        router = sirene_router(routes, naf=naf)
        with mock.patch(GET_COMPANY, new=router):
            return INSEEApiClient.fetch_by_siret(siret), router


class FetchHeadOfficeTests(InseeClientTestCase):
    """``fetch_by_siret`` for a head office and for a secondary establishment."""

    def test_head_office_needs_a_single_call(self):
        """For a head office there is one request and the head office is itself."""
        data, router = self.fetch({SIRET_SIEGE: ok("etab_siege_actif.json")})
        self.assertEqual(
            sirene_urls(router), [f"{INSEEApiClient.BASE_URL}/siret/{SIRET_SIEGE}"]
        )
        self.assertEqual(data["headquarters_siret"], SIRET_SIEGE)
        self.assertEqual(data["headquarters_address"], data["address"])
        self.assertEqual(data["headquarters_state"], "A")

    def test_data_of_a_head_office(self):
        """The main fields are read and formatted."""
        data, _ = self.fetch({SIRET_SIEGE: ok("etab_siege_actif.json")})
        self.assertEqual(data["name"], "ACME INDUSTRIES")
        self.assertEqual(data["siret"], SIRET_SIEGE)
        self.assertEqual(data["siren"], "123456782")
        self.assertEqual(data["address"], "10 RUE DE LA PAIX, 75002 PARIS")
        self.assertEqual(data["legal_structure"], "5710")
        self.assertEqual(data["company_size_category"], "PME")
        self.assertEqual(data["business_line"], "62.01Z")
        self.assertEqual(data["creation_date"], "2010-01-01")
        self.assertEqual(data["establishment_state"], "A")
        self.assertEqual(data["closure_date"], "")

    def test_secondary_establishment_reads_the_head_office(self):
        """A second request asks SIREN + ``nicSiegeUniteLegale`` for the head office."""
        data, router = self.fetch(
            {
                SIRET_SECONDAIRE: ok("etab_secondaire.json"),
                SIRET_SIEGE: ok("etab_siege_du_secondaire.json"),
            },
            siret=SIRET_SECONDAIRE,
        )
        base = INSEEApiClient.BASE_URL
        self.assertEqual(
            sirene_urls(router),
            [f"{base}/siret/{SIRET_SECONDAIRE}", f"{base}/siret/{SIRET_SIEGE}"],
        )
        self.assertEqual(data["siret"], SIRET_SECONDAIRE)
        self.assertEqual(data["address"], "5 AV JEAN JAURES, 69007 LYON")
        self.assertEqual(data["headquarters_siret"], SIRET_SIEGE)
        self.assertEqual(data["headquarters_address"], "10 RUE DE LA PAIX, 75002 PARIS")
        self.assertEqual(data["headquarters_state"], "A")

    def test_unreadable_head_office_keeps_its_siret_only(self):
        """If the second request fails, the head office SIRET is kept without details."""
        data, router = self.fetch(
            {SIRET_SECONDAIRE: ok("etab_secondaire.json")}, siret=SIRET_SECONDAIRE
        )
        self.assertEqual(len(sirene_urls(router)), 2)
        self.assertEqual(data["headquarters_siret"], SIRET_SIEGE)
        self.assertEqual(data["headquarters_address"], "")
        self.assertEqual(data["headquarters_state"], "")

    def test_missing_nic_gives_no_head_office(self):
        """Without ``nicSiegeUniteLegale`` there is no second request and no head office."""
        payload = load_fixture("etab_secondaire.json")
        del payload["etablissement"]["uniteLegale"]["nicSiegeUniteLegale"]
        data, router = self.fetch(
            {SIRET_SECONDAIRE: fake_response(200, payload)}, siret=SIRET_SECONDAIRE
        )
        self.assertEqual(len(sirene_urls(router)), 1)
        self.assertEqual(data["headquarters_siret"], "")


class FetchActivityTests(InseeClientTestCase):
    """NAF 2025 activity: establishment first, then legal unit."""

    def test_activity_of_the_establishment_and_its_label(self):
        """The code of the establishment is used and its label is read."""
        data, router = self.fetch({SIRET_SIEGE: ok("etab_siege_actif.json")})
        self.assertEqual(data["activity_naf25"], "62.01Z")
        self.assertEqual(data["activity_naf25_label"], "Programmation informatique")
        self.assertEqual(
            naf_urls(router),
            ["https://id.insee.fr/codes/naf2025/sousClasse/62.01Z"],
        )

    def test_activity_falls_back_to_the_legal_unit(self):
        """Without code on the establishment, the one of the legal unit is used."""
        data, _ = self.fetch(
            {
                SIRET_SECONDAIRE: ok("etab_secondaire.json"),
                SIRET_SIEGE: ok("etab_siege_du_secondaire.json"),
            },
            siret=SIRET_SECONDAIRE,
        )
        self.assertEqual(data["activity_naf25"], "62.10Z")

    def test_no_activity_at_all(self):
        """Without any NAF 2025 code both fields are empty and the label is not asked."""
        data, router = self.fetch({SIRET_SIEGE: ok("etab_sans_naf25.json")})
        self.assertEqual(data["activity_naf25"], "")
        self.assertEqual(data["activity_naf25_label"], "")
        self.assertEqual(naf_urls(router), [])

    def test_label_service_down_keeps_the_code(self):
        """If the label cannot be read, the code is still returned."""
        data, _ = self.fetch(
            {SIRET_SIEGE: ok("etab_siege_actif.json")}, naf=requests.ConnectionError
        )
        self.assertEqual(data["activity_naf25"], "62.01Z")
        self.assertEqual(data["activity_naf25_label"], "")


class FetchFailureTests(InseeClientTestCase):
    """Every failure gives ``None`` instead of an exception."""

    def test_unknown_siret(self):
        """A 404 gives None."""
        data, _ = self.fetch({})
        self.assertIsNone(data)

    def test_server_error(self):
        """A 500 gives None."""
        data, _ = self.fetch({SIRET_SIEGE: fake_response(500, {})})
        self.assertIsNone(data)

    def test_timeout_and_connection_errors(self):
        """Network errors are swallowed."""
        for error in (requests.Timeout, requests.ConnectionError):
            with self.subTest(error=error.__name__):
                with mock.patch(GET_COMPANY, side_effect=error):
                    self.assertIsNone(INSEEApiClient.fetch_by_siret(SIRET_SIEGE))

    def test_unexpected_json(self):
        """A 200 without establishment gives None."""
        for payload in ({}, {"header": {}}, {"etablissements": []}):
            with self.subTest(payload=payload):
                data, _ = self.fetch({SIRET_SIEGE: fake_response(200, payload)})
                self.assertIsNone(data)

    def test_establishment_list_fallback(self):
        """An ``etablissements`` list is accepted when ``etablissement`` is missing."""
        etab = load_fixture("etab_siege_actif.json")["etablissement"]
        data, _ = self.fetch(
            {SIRET_SIEGE: fake_response(200, {"etablissements": [etab]})}
        )
        self.assertEqual(data["siret"], SIRET_SIEGE)


class HeadersTests(SimpleTestCase):
    """``get_headers`` and the request made."""

    def test_headers_carry_the_api_key(self):
        """The key comes from the settings and the API is asked for JSON."""
        headers = INSEEApiClient.get_headers()
        self.assertEqual(headers["X-INSEE-Api-Key-Integration"], "test")
        self.assertEqual(headers["Accept"], "application/json")

    def test_request_uses_headers_and_timeout(self):
        """``requests.get`` receives the headers and a timeout."""
        router = sirene_router({})
        with mock.patch(GET_COMPANY, new=router):
            INSEEApiClient.fetch_by_siret(SIRET_SIEGE)
        kwargs = router.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-INSEE-Api-Key-Integration"], "test")
        self.assertEqual(kwargs["timeout"], 5)


class FormatEtablissementTests(SimpleTestCase):
    """``_format_etablissement_data`` on fixtures and hand-made data."""

    format = staticmethod(INSEEApiClient._format_etablissement_data)

    def test_vat_number_is_computed_from_the_siren(self):
        """The VAT number is ``FR`` + key + SIREN."""
        data = self.format(load_fixture("etab_siege_actif.json")["etablissement"], "x")
        self.assertEqual(data["vat_number"], "FR11123456782")

    def test_closed_establishment_dates_the_closure(self):
        """The closing date is the start of the period that changed the state to closed."""
        data = self.format(load_fixture("etab_ferme.json")["etablissement"], "x")
        self.assertEqual(data["establishment_state"], "F")
        self.assertEqual(data["closure_date"], "2023-03-01")

    def test_ceased_legal_unit(self):
        """The state of the legal unit is reported."""
        data = self.format(
            load_fixture("unite_legale_cessee.json")["etablissement"], "x"
        )
        self.assertEqual(data["unit_state"], "C")

    def test_individual_name_when_no_denomination(self):
        """A sole trader is named after first and last name."""
        etab = {
            "uniteLegale": {
                "prenomUsuelUniteLegale": "Ada",
                "nomUniteLegale": "Lovelace",
            }
        }
        self.assertEqual(self.format(etab, "x")["name"], "Ada Lovelace")

    def test_siren_and_siret_fallbacks(self):
        """Missing SIREN and SIRET are taken from the SIRET that was asked."""
        data = self.format({}, SIRET_SIEGE)
        self.assertEqual(data["siret"], SIRET_SIEGE)
        self.assertEqual(data["siren"], "123456782")

    def test_no_vat_number_without_a_valid_siren(self):
        """A SIREN that is not 9 digits gives no VAT number."""
        self.assertEqual(self.format({"siren": "12ab"}, "x")["vat_number"], "")

    def test_empty_establishment(self):
        """An empty answer gives empty strings, never an exception."""
        data = self.format({}, "short")
        self.assertEqual((data["name"], data["address"], data["siren"]), ("", "", ""))
        self.assertEqual(data["establishment_state"], "")

    def test_business_line_falls_back_to_the_legal_unit(self):
        """The activity of the current period wins over the one of the legal unit."""
        etab = {
            "uniteLegale": {"activitePrincipaleUniteLegale": "11.11A"},
            "periodesEtablissement": [{"activitePrincipaleEtablissement": "22.22B"}],
        }
        self.assertEqual(self.format(etab, "x")["business_line"], "22.22B")
        etab["periodesEtablissement"] = []
        self.assertEqual(self.format(etab, "x")["business_line"], "11.11A")
