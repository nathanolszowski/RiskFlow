"""Tests for the Sirene synchronisation and refresh (crm/services/company.py).

The network is patched (see ``crm/tests/helpers.py``), the cache is cleared in
``setUp`` and the data comes from the fixtures.
"""

from datetime import date
from unittest import mock

from accounts.tests.factories import UserFactory
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from crm.models import Company
from crm.services.company import (
    SIRENE_FIELDS,
    INSEEApiClient,
    _describe_state,
    apply_sirene_changes,
    get_administrative_state,
    get_cessation_alert,
    get_sirene_changes,
    get_sirene_data,
    get_sirene_data_cached,
    sync_sirene_status,
)
from crm.tests.factories import CompanyFactory
from crm.tests.helpers import (
    GET_COMPANY,
    SIRET_SECONDAIRE,
    SIRET_SIEGE,
    fake_response,
    load_fixture,
    sirene_router,
    sirene_urls,
)


def routes(*fixtures):
    """Build the Sirene routes of a fake API from fixture files.

    Args:
        *fixtures: Pairs ``(siret, fixture name)``.

    Returns:
        A mapping ``{siret: 200 response}``.
    """
    return {siret: fake_response(200, load_fixture(name)) for siret, name in fixtures}


class SireneTestCase(TestCase):
    """Base class: clear the cache and offer ``network`` / ``fresh_data``."""

    def setUp(self):
        """Clear the cache, so that no answer is reused between tests."""
        super().setUp()
        cache.clear()

    def network(self, mapping):
        """Patch ``requests.get`` with a fake Sirene API for the rest of the test.

        Args:
            mapping: Routes of the fake API, see ``routes``.

        Returns:
            The fake network (a mock recording the URLs asked).
        """
        router = sirene_router(mapping)
        patcher = mock.patch(GET_COMPANY, new=router)
        patcher.start()
        self.addCleanup(patcher.stop)
        return router

    def fresh_data(self, fixture="etab_siege_actif.json", siret=SIRET_SIEGE):
        """Return the data the client builds from a fixture.

        Args:
            fixture: Fixture file name.
            siret: SIRET of the fixture.

        Returns:
            The formatted Sirene data.
        """
        with mock.patch(GET_COMPANY, new=sirene_router(routes((siret, fixture)))):
            return INSEEApiClient.fetch_by_siret(siret)


class CachedDataTests(SireneTestCase):
    """``get_sirene_data_cached`` and ``get_sirene_data``."""

    def test_second_call_is_served_by_the_cache(self):
        """Two lookups of the same SIRET make a single Sirene request."""
        router = self.network(routes((SIRET_SIEGE, "etab_siege_actif.json")))
        first = get_sirene_data_cached(SIRET_SIEGE)
        second = get_sirene_data_cached(SIRET_SIEGE)
        self.assertEqual(first, second)
        self.assertEqual(len(sirene_urls(router)), 1)

    def test_failure_is_not_cached(self):
        """A failed lookup is retried at the next call."""
        router = self.network({})
        self.assertIsNone(get_sirene_data_cached(SIRET_SIEGE))
        self.assertIsNone(get_sirene_data_cached(SIRET_SIEGE))
        self.assertEqual(len(sirene_urls(router)), 2)
        router.side_effect = sirene_router(
            routes((SIRET_SIEGE, "etab_siege_actif.json"))
        ).side_effect
        self.assertIsNotNone(get_sirene_data_cached(SIRET_SIEGE))

    def test_get_sirene_data_needs_a_valid_siret(self):
        """A SIRET that is not 14 digits gives None without any request."""
        router = self.network({})
        for siret in ("", "123", "1234567820001X", " " * 14):
            with self.subTest(siret=siret):
                company = CompanyFactory.build(siret=siret)
                self.assertIsNone(get_sirene_data(company))
        self.assertEqual(router.call_count, 0)

    def test_get_sirene_data_never_uses_the_cache(self):
        """The refresh of an existing client always asks the API."""
        router = self.network(routes((SIRET_SIEGE, "etab_siege_actif.json")))
        company = CompanyFactory(siret=SIRET_SIEGE)
        get_sirene_data(company)
        get_sirene_data(company)
        self.assertEqual(len(sirene_urls(router)), 2)


class AdministrativeStateTests(SimpleTestCase):
    """``get_administrative_state``, ``get_cessation_alert`` and ``_describe_state``."""

    def test_states(self):
        """The state is derived from the unit and establishment states."""
        cases = [
            ({"unit_state": "C"}, ("C", None)),
            ({"unit_state": "C", "establishment_state": "F"}, ("C", None)),
            (
                {"establishment_state": "F", "closure_date": "2023-03-01"},
                ("F", date(2023, 3, 1)),
            ),
            ({"establishment_state": "F", "closure_date": ""}, ("F", None)),
            ({"establishment_state": "F", "closure_date": "garbage"}, ("F", None)),
            ({"establishment_state": "A", "unit_state": "A"}, ("A", None)),
            ({"unit_state": "A"}, ("A", None)),
            ({}, ("", None)),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(get_administrative_state(data), expected)

    def test_cessation_alert(self):
        """Only a ceased or closed state gives an alert, with the head office state."""
        hq = {"headquarters_state": "A", "headquarters_address": "1 rue X"}
        self.assertIsNone(get_cessation_alert({"establishment_state": "A", **hq}))
        self.assertIsNone(get_cessation_alert({}))
        ceased = get_cessation_alert({"unit_state": "C", **hq})
        self.assertEqual(
            ceased,
            {"kind": "ceased", "since": None, "hq_state": "A", "hq_address": "1 rue X"},
        )
        closed = get_cessation_alert(
            {"establishment_state": "F", "closure_date": "2023-03-01", **hq}
        )
        self.assertEqual(closed["kind"], "closed")
        self.assertEqual(closed["since"], date(2023, 3, 1))

    def test_describe_state(self):
        """The labels shown in the update modal."""
        self.assertEqual(_describe_state("", None), "Non vérifié")
        self.assertEqual(_describe_state("A", None), "Actif")
        self.assertEqual(_describe_state("C", None), "Entreprise cessée")
        self.assertEqual(_describe_state("F", None), "Établissement fermé")
        self.assertEqual(
            _describe_state("F", date(2023, 3, 1)),
            "Établissement fermé depuis le 01/03/2023",
        )


class SyncSireneStatusTests(SireneTestCase):
    """``sync_sirene_status`` right after the creation of a client."""

    def setUp(self):
        """Create a client and the user who creates it."""
        super().setUp()
        self.user = UserFactory()
        self.company = CompanyFactory(siret=SIRET_SIEGE, siren="123456782")

    def reload(self):
        """Return the company as stored in the database.

        Returns:
            The refreshed company.
        """
        return Company.objects.get(pk=self.company.pk)

    def test_invalid_siret_does_nothing(self):
        """An invalid SIRET writes nothing and asks nothing."""
        router = self.network({})
        company = CompanyFactory(siret="123")
        sync_sirene_status(company, self.user)
        self.assertEqual(router.call_count, 0)
        self.assertEqual(self.reload().administrative_state, "")

    def test_silent_api_does_nothing(self):
        """If the API cannot be reached nothing is written."""
        self.network({})
        sync_sirene_status(self.company, self.user)
        company = self.reload()
        self.assertEqual(company.administrative_state, "")
        self.assertEqual(company.activity_naf25, "")
        self.assertNotEqual(company.updated_by, self.user)

    def test_state_head_office_and_activity_are_stored(self):
        """The state, the head office and the NAF 2025 activity are saved."""
        self.network(routes((SIRET_SIEGE, "etab_siege_actif.json")))
        sync_sirene_status(self.company, self.user)
        company = self.reload()
        self.assertEqual(company.administrative_state, "A")
        self.assertEqual(company.headquarters_siret, SIRET_SIEGE)
        self.assertEqual(company.headquarters_address, "10 RUE DE LA PAIX, 75002 PARIS")
        self.assertEqual(company.headquarters_state, "A")
        self.assertEqual(company.activity_naf25, "62.01Z")
        self.assertEqual(company.activity_naf25_label, "Programmation informatique")
        self.assertEqual(company.updated_by, self.user)

    def test_closed_establishment_stores_the_closure_date(self):
        """A closed establishment is stored with its closing date."""
        company = CompanyFactory(siret=SIRET_SECONDAIRE)
        self.network(
            routes(
                (SIRET_SECONDAIRE, "etab_ferme.json"),
                (SIRET_SIEGE, "etab_siege_du_secondaire.json"),
            )
        )
        sync_sirene_status(company, self.user)
        company.refresh_from_db()
        self.assertEqual(company.administrative_state, "F")
        self.assertEqual(company.closure_date, date(2023, 3, 1))
        self.assertEqual(company.headquarters_siret, SIRET_SIEGE)

    def test_state_is_kept_when_the_api_gives_none(self):
        """No state in the answer leaves the stored state untouched."""
        company = (
            CompanyFactory(siret=SIRET_SIEGE + "", closed=True)
            if False
            else self.company
        )
        payload = load_fixture("etab_siege_actif.json")
        etab = payload["etablissement"]
        etab["uniteLegale"].pop("etatAdministratifUniteLegale")
        etab["periodesEtablissement"][0].pop("etatAdministratifEtablissement")
        Company.objects.filter(pk=company.pk).update(administrative_state="F")
        company.refresh_from_db()
        self.network({SIRET_SIEGE: fake_response(200, payload)})
        sync_sirene_status(company, self.user)
        self.assertEqual(self.reload().administrative_state, "F")


class SireneChangesTests(SireneTestCase):
    """``get_sirene_changes``: what differs between the client and fresh data."""

    def setUp(self):
        """Create a client identical to the head office fixture."""
        super().setUp()
        self.data = self.fresh_data()
        self.company = CompanyFactory(
            siret=SIRET_SIEGE,
            siren=self.data["siren"],
            name=self.data["name"],
            address=self.data["address"],
            legal_structure=self.data["legal_structure"],
            company_size_category=self.data["company_size_category"],
            business_line=self.data["business_line"],
            creation_date=date(2010, 1, 1),
            vat_number=self.data["vat_number"],
            activity_naf25="62.01Z",
            activity_naf25_label="Programmation informatique",
            headquarters_siret=SIRET_SIEGE,
            headquarters_address=self.data["address"],
            headquarters_state="A",
            administrative_state="A",
        )

    def fields(self, changes):
        """Return the names of the changed fields.

        Args:
            changes: Result of ``get_sirene_changes``.

        Returns:
            A set of field names.
        """
        return {c["field"] for c in changes}

    def test_identical_data_gives_no_change(self):
        """A client in sync with Sirene has nothing to update."""
        self.assertEqual(get_sirene_changes(self.company, self.data), [])

    def test_changed_field_is_listed_with_current_and_new_values(self):
        """A different name is listed with both values to display."""
        self.company.name = "Ancien nom"
        changes = get_sirene_changes(self.company, self.data)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["field"], "name")
        self.assertEqual(changes[0]["current"], "Ancien nom")
        self.assertEqual(changes[0]["new"], "ACME INDUSTRIES")
        self.assertEqual(changes[0]["label"], "Nom du client")

    def test_empty_api_value_is_ignored(self):
        """A field the API returns empty never appears as a change."""
        self.company.name = "Ancien nom"
        self.data["name"] = ""
        self.assertEqual(get_sirene_changes(self.company, self.data), [])

    def test_only_sirene_fields_are_compared(self):
        """Data keys outside ``SIRENE_FIELDS`` never produce a change."""
        self.data.update(siret="99999999999999", website="https://x.fr", nb_employees=5)
        self.assertEqual(get_sirene_changes(self.company, self.data), [])
        self.assertNotIn("siret", SIRENE_FIELDS)
        for forbidden in ("website", "labels", "executive_board", "nb_employees"):
            self.assertNotIn(forbidden, SIRENE_FIELDS)

    def test_labels_are_shown_for_codes(self):
        """A legal form is shown with its label, the head office state as well."""
        self.company.legal_structure = "5499"
        self.company.headquarters_state = "F"
        changes = {c["field"]: c for c in get_sirene_changes(self.company, self.data)}
        self.assertEqual(
            changes["legal_structure"]["new"], "SAS, société par actions simplifiée"
        )
        self.assertEqual(
            changes["legal_structure"]["current"],
            "Société à responsabilité limitée (sans autre indication)",
        )
        self.assertEqual(
            changes["headquarters_state"]["current"], "Établissement fermé"
        )
        self.assertEqual(changes["headquarters_state"]["new"], "Actif")

    def test_naf_label_alone_is_proposed(self):
        """A new label for the same code is proposed, shown as ``label (code)``."""
        self.company.activity_naf25_label = "Ancien libellé"
        changes = get_sirene_changes(self.company, self.data)
        self.assertEqual(self.fields(changes), {"activity_naf25"})
        self.assertEqual(changes[0]["new"], "Programmation informatique (62.01Z)")
        self.assertEqual(changes[0]["current"], "Ancien libellé (62.01Z)")

    def test_state_change_for_a_never_checked_client(self):
        """A client never checked gets the state proposed, even ``active``."""
        self.company.administrative_state = ""
        changes = get_sirene_changes(self.company, self.data)
        self.assertEqual(self.fields(changes), {"administrative_state"})
        self.assertEqual(changes[0]["current"], "Non vérifié")
        self.assertEqual(changes[0]["new"], "Actif")

    def test_state_change_to_ceased(self):
        """A ceased company is proposed as such."""
        data = self.fresh_data("unite_legale_cessee.json")
        changes = {c["field"]: c for c in get_sirene_changes(self.company, data)}
        self.assertEqual(changes["administrative_state"]["new"], "Entreprise cessée")


class ApplySireneChangesTests(SireneTestCase):
    """``apply_sirene_changes``: the user's selection, the whitelist and the safeguards."""

    def setUp(self):
        """Create a client that differs from Sirene on several fields."""
        super().setUp()
        self.user = UserFactory()
        self.data = self.fresh_data()
        self.company = CompanyFactory(
            siret=SIRET_SIEGE,
            siren="123456782",
            name="Ancien nom",
            address="Ancienne adresse",
            creation_date=date(2000, 1, 1),
            website="https://client.example",
            labels="ISO 9001",
            executive_board="Conseil",
            nb_employees=42,
        )

    def reload(self):
        """Return the company as stored in the database.

        Returns:
            The refreshed company.
        """
        return Company.objects.get(pk=self.company.pk)

    def apply(self, selected, data=None):
        """Apply a selection on the company.

        Args:
            selected: Names of the accepted fields.
            data: Fresh data, by default the head office fixture.

        Returns:
            The list of updated fields.
        """
        return apply_sirene_changes(
            self.company, self.user, data or self.data, selected
        )

    def test_only_selected_fields_are_applied(self):
        """An unticked field keeps its value."""
        updated = self.apply(["name"])
        self.assertEqual(updated, ["name"])
        company = self.reload()
        self.assertEqual(company.name, "ACME INDUSTRIES")
        self.assertEqual(company.address, "Ancienne adresse")
        self.assertEqual(company.updated_by, self.user)

    def test_fields_outside_the_whitelist_are_ignored(self):
        """``siret``, ``website``, ``labels``... cannot be written even if selected."""
        self.data.update(
            siret="99999999999999", website="https://hacked.example", labels="x"
        )
        updated = self.apply(
            [
                "siret",
                "website",
                "labels",
                "executive_board",
                "nb_employees",
                "is_active",
            ]
        )
        self.assertEqual(updated, [])
        company = self.reload()
        self.assertEqual(company.siret, SIRET_SIEGE)
        self.assertEqual(company.website, "https://client.example")
        self.assertEqual(company.labels, "ISO 9001")
        self.assertEqual(company.executive_board, "Conseil")
        self.assertEqual(company.nb_employees, 42)

    def test_applying_everything_never_touches_protected_fields(self):
        """Even with every change accepted, the protected fields stay as they were."""
        selected = [*SIRENE_FIELDS, "administrative_state"]
        self.apply(selected)
        company = self.reload()
        self.assertEqual(
            (
                company.siret,
                company.website,
                company.labels,
                company.executive_board,
                company.nb_employees,
            ),
            (SIRET_SIEGE, "https://client.example", "ISO 9001", "Conseil", 42),
        )
        self.assertEqual(company.address, "10 RUE DE LA PAIX, 75002 PARIS")
        self.assertEqual(company.creation_date, date(2010, 1, 1))

    def test_empty_api_value_does_not_erase(self):
        """A field the API returns empty is not applied, even when selected."""
        self.data["name"] = ""
        self.assertEqual(self.apply(["name"]), [])
        self.assertEqual(self.reload().name, "Ancien nom")

    def test_unchanged_field_is_not_reported(self):
        """A selected field that did not change is not written nor returned."""
        self.company.siren = "123456782"
        self.assertEqual(self.apply(["siren"]), [])

    def test_values_come_from_the_api_data(self):
        """The written value is the one of the data, not something posted."""
        self.apply(["address"])
        self.assertEqual(self.reload().address, self.data["address"])

    def test_state_writes_the_closure_date_too(self):
        """Accepting the state writes ``administrative_state`` and ``closure_date``."""
        data = self.fresh_data("etab_ferme.json", siret=SIRET_SECONDAIRE)
        self.assertEqual(
            self.apply(["administrative_state"], data), ["administrative_state"]
        )
        company = self.reload()
        self.assertEqual(company.administrative_state, "F")
        self.assertEqual(company.closure_date, date(2023, 3, 1))

    def test_naf_code_writes_its_label_too(self):
        """Accepting the NAF 2025 code also writes its label."""
        self.apply(["activity_naf25"])
        company = self.reload()
        self.assertEqual(company.activity_naf25, "62.01Z")
        self.assertEqual(company.activity_naf25_label, "Programmation informatique")

    def test_unreadable_date_is_refused(self):
        """An unreadable creation date raises ValidationError and writes nothing."""
        self.data["creation_date"] = "pas une date"
        with self.assertRaisesMessage(ValidationError, "date illisible"):
            self.apply(["creation_date"])
        self.assertEqual(self.reload().creation_date, date(2000, 1, 1))

    def test_empty_selection_changes_nothing(self):
        """Nothing selected, nothing written."""
        self.assertEqual(self.apply([]), [])
        self.assertEqual(self.reload().name, "Ancien nom")
