"""Tests of the geocoding service: search, suggestions and certification of an address."""

from unittest import mock

import requests
from accounts.tests.factories import UserFactory
from django.core.cache import cache
from django.test import TestCase, override_settings

from core.services.geo import (
    GeocodingUnavailable,
    certify_address,
    geocode,
    suggest,
)

from .helpers import GEOCODING_GET, geo_response, load_geo_fixture

ADDRESS = "12 Rue de la Paix, 75002 Paris"


class GeoTestCase(TestCase):
    """Base class: geocoding on, cache cleared, network replaced by a mock."""

    def setUp(self):
        """Turn the geocoding on and install the fake network."""
        super().setUp()
        cache.clear()
        settings_override = override_settings(GEOCODING_ENABLED=True)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.get = self.patch(
            geo_response(200, load_geo_fixture("geopf_search_housenumber.json"))
        )

    def patch(self, response):
        """Make ``requests.get`` answer with a response (or raise an exception).

        Args:
            response: Fake response, or an exception to raise.

        Returns:
            The mock replacing ``requests.get``.
        """
        patcher = mock.patch(GEOCODING_GET)
        get = patcher.start()
        self.addCleanup(patcher.stop)
        if isinstance(response, Exception):
            get.side_effect = response
        else:
            get.return_value = response
        return get

    def make_user(self, **fields):
        """Create a user with a home address.

        Args:
            **fields: Address fields.

        Returns:
            The saved user.
        """
        values = {
            "address_line": "12 Rue de la Paix",
            "postal_code": "75002",
            "city": "Paris",
        }
        return UserFactory(**{**values, **fields})


class GeocodeTests(GeoTestCase):
    """``geocode`` returns a reliable match or None, and raises when the service is down."""

    def test_returns_the_coordinates_of_a_found_address(self):
        """A house number match gives its coordinates and its parts."""
        result = geocode(ADDRESS)
        self.assertEqual(result.address_line, "12 Rue de la Paix")
        self.assertEqual((result.postal_code, result.city), ("75002", "Paris"))
        self.assertEqual(result.citycode, "75102")
        self.assertAlmostEqual(float(result.latitude), 48.869141, places=5)
        self.assertAlmostEqual(float(result.longitude), 2.331303, places=5)

    def test_asks_the_address_index_with_one_result(self):
        """The request targets the address index, with the text and one candidate."""
        geocode(ADDRESS)
        url = self.get.call_args.args[0]
        params = self.get.call_args.kwargs["params"]
        self.assertEqual(url, "https://geocodage.test/search")
        self.assertEqual(params, {"index": "address", "q": ADDRESS, "limit": 1})

    def test_a_municipality_is_not_precise_enough(self):
        """A match on the municipality only is not certifiable."""
        self.patch(
            geo_response(200, load_geo_fixture("geopf_search_municipality.json"))
        )
        self.assertIsNone(geocode("Amiens"))

    def test_nothing_found_returns_none(self):
        """An address the geocoder does not know gives None."""
        self.patch(geo_response(200, load_geo_fixture("geopf_search_empty.json")))
        self.assertIsNone(geocode("zzzz"))

    @override_settings(GEOCODING_MIN_SCORE=0.99)
    def test_a_low_score_is_refused(self):
        """A match below the minimum score is not certifiable."""
        self.assertIsNone(geocode(ADDRESS))

    def test_blank_address_does_not_call_the_service(self):
        """An empty address is not searched."""
        self.assertIsNone(geocode("  "))
        self.get.assert_not_called()

    def test_service_errors_raise(self):
        """A network error, an HTTP error and a broken body raise ``GeocodingUnavailable``."""
        for response in (
            requests.ConnectionError("down"),
            geo_response(429, {}),
            geo_response(200, ValueError("not json")),
        ):
            self.patch(response)
            with self.assertRaises(GeocodingUnavailable):
                geocode(ADDRESS)

    @override_settings(GEOCODING_ENABLED=False)
    def test_disabled_service_is_unavailable(self):
        """With the geocoding turned off nothing is called."""
        with self.assertRaises(GeocodingUnavailable):
            geocode(ADDRESS)
        self.get.assert_not_called()


class SuggestTests(GeoTestCase):
    """``suggest`` feeds the autocompletion."""

    def setUp(self):
        """Serve the suggestions fixture."""
        super().setUp()
        self.get = self.patch(
            geo_response(200, load_geo_fixture("geopf_search_suggestions.json"))
        )

    def test_returns_the_matches(self):
        """The typed text gives the matching addresses, in autocompletion mode."""
        results = suggest("12 rue de la paix par")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].label, "12 Rue de la Paix 75002 Paris")
        self.assertEqual(self.get.call_args.kwargs["params"]["autocomplete"], 1)

    def test_short_text_is_not_searched(self):
        """Less than three characters give no suggestion and no request."""
        self.assertEqual(suggest("12"), [])
        self.get.assert_not_called()

    def test_same_text_is_served_from_the_cache(self):
        """Typing the same text again does not call the service again."""
        suggest("12 rue de la paix par")
        suggest("  12 RUE de la paix par ")
        self.assertEqual(self.get.call_count, 1)

    def test_service_failure_gives_no_suggestion(self):
        """A failing service gives an empty list instead of an error."""
        self.patch(requests.ConnectionError("down"))
        self.assertEqual(suggest("12 rue de la paix"), [])


class CertifyAddressTests(GeoTestCase):
    """``certify_address`` stores the coordinates and only recomputes them when needed."""

    def test_certifies_and_stores_the_coordinates(self):
        """A found address is certified with its coordinates, kept in the database."""
        user = self.make_user()
        self.assertTrue(certify_address(user))
        user.refresh_from_db()
        self.assertTrue(user.address_certified)
        self.assertAlmostEqual(float(user.latitude), 48.869141, places=5)
        self.assertEqual(user.geocoded_address, ADDRESS)
        self.assertEqual(user.citycode, "75102")
        self.assertIsNotNone(user.geocoded_at)

    def test_does_not_geocode_again_when_the_address_is_unchanged(self):
        """Once geocoded, an unchanged address is never searched again."""
        user = self.make_user()
        certify_address(user)
        self.assertTrue(certify_address(user))
        self.assertEqual(self.get.call_count, 1)

    def test_force_geocodes_again(self):
        """``force`` searches again even if the address did not change."""
        user = self.make_user()
        certify_address(user)
        certify_address(user, force=True)
        self.assertEqual(self.get.call_count, 2)

    def test_changing_the_address_drops_the_coordinates_on_save(self):
        """Editing the address clears the stale coordinates, with no network call."""
        user = self.make_user()
        certify_address(user)
        user.city = "Lyon"
        user.save()
        user.refresh_from_db()
        self.assertFalse(user.address_certified)
        self.assertIsNone(user.latitude)
        self.assertEqual(self.get.call_count, 1)

    def test_changing_the_address_geocodes_the_new_one(self):
        """After an edit the next certification searches the new address."""
        user = self.make_user()
        certify_address(user)
        user.address_line = "1 Rue X"
        user.save()
        certify_address(user)
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(
            self.get.call_args.kwargs["params"]["q"], "1 Rue X, 75002 Paris"
        )

    def test_unknown_address_is_stored_as_not_certified(self):
        """An address that is not found is not certified and is not searched again."""
        get = self.patch(geo_response(200, load_geo_fixture("geopf_search_empty.json")))
        user = self.make_user()
        self.assertFalse(certify_address(user))
        user.refresh_from_db()
        self.assertFalse(user.address_certified)
        self.assertIsNone(user.latitude)
        self.assertIsNotNone(user.geocoded_at)
        certify_address(user)
        self.assertEqual(get.call_count, 1)

    def test_service_down_never_raises_and_is_retried(self):
        """A failure leaves the address uncertified and tries again next time."""
        get = self.patch(requests.ConnectionError("down"))
        user = self.make_user()
        self.assertFalse(certify_address(user))
        user.refresh_from_db()
        self.assertIsNone(user.geocoded_at)
        certify_address(user)
        self.assertEqual(get.call_count, 2)

    def test_forced_retry_with_service_down_keeps_the_coordinates(self):
        """A forced recertification that fails keeps the coordinates already stored."""
        user = self.make_user()
        certify_address(user)
        self.patch(requests.ConnectionError("down"))
        self.assertTrue(certify_address(user, force=True))
        user.refresh_from_db()
        self.assertTrue(user.address_certified)
        self.assertIsNotNone(user.latitude)

    def test_empty_address_is_not_searched(self):
        """An instance without address makes no request and writes nothing."""
        user = self.make_user(address_line="", postal_code="", city="")
        self.assertFalse(certify_address(user))
        self.get.assert_not_called()

    def test_emptying_the_address_clears_the_coordinates(self):
        """Removing the address removes the certification."""
        user = self.make_user()
        certify_address(user)
        user.address_line = user.postal_code = user.city = ""
        user.save()
        self.assertFalse(certify_address(user))
        user.refresh_from_db()
        self.assertFalse(user.address_certified)
        self.assertIsNone(user.longitude)
        self.assertEqual(self.get.call_count, 1)

    def test_posted_coordinates_cannot_be_set_by_a_form(self):
        """The coordinates are not editable: no model form can write them."""
        from accounts.forms import AddressForm

        form = AddressForm(
            {
                "address_line": "1 rue X",
                "postal_code": "75002",
                "city": "Paris",
                "latitude": "1",
                "longitude": "2",
                "address_certified": "on",
            }
        )
        self.assertNotIn("latitude", form.fields)
        self.assertNotIn("address_certified", form.fields)
