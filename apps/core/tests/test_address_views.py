"""Tests of the address autocompletion view and the certification wired in the forms."""

from unittest import mock

import requests
from accounts.tests.factories import UserFactory
from crm.tests.factories import CompanyFactory
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from inspections.models import InspectionFolder
from inspections.tests.factories import InspectionFolderFactory

from .helpers import (
    GEOCODING_GET,
    HtmxClientMixin,
    geo_response,
    geo_router,
    load_geo_fixture,
)

SUGGESTIONS = "core/partials/ui/address_suggestions.html"


@override_settings(GEOCODING_ENABLED=True)
class AddressSuggestionsViewTests(HtmxClientMixin, TestCase):
    """``core:address_suggestions`` feeds the street autocompletion."""

    url = reverse("core:address_suggestions")

    def setUp(self):
        """Clear the cache and serve the suggestions fixture."""
        super().setUp()
        cache.clear()
        patcher = mock.patch(
            GEOCODING_GET,
            new=geo_router(
                search=geo_response(
                    200, load_geo_fixture("geopf_search_suggestions.json")
                )
            ),
        )
        self.router = patcher.start()
        self.addCleanup(patcher.stop)

    def test_lists_the_suggestions_with_their_parts(self):
        """Each suggestion carries the street, postal code and city to pre-fill."""
        response = self.htmx_get(self.url, {"address_line": "12 rue de la paix par"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, SUGGESTIONS)
        self.assertContains(response, 'data-address-line="12 Rue de la Paix"')
        self.assertContains(response, 'data-postal-code="75002"')
        self.assertContains(response, 'data-city="Paris"')

    def test_accepts_a_starting_point_field(self):
        """The trip form types its text in ``origin_address``."""
        response = self.htmx_get(self.url, {"origin_address": "12 rue de la paix par"})
        self.assertContains(response, "data-address-suggestion")

    def test_short_text_gives_an_empty_answer(self):
        """Too little text calls nothing and renders no list."""
        response = self.htmx_get(self.url, {"address_line": "12"})
        self.assertNotContains(response, "data-address-suggestion")
        self.router.assert_not_called()

    def test_service_down_gives_an_empty_answer(self):
        """The user keeps typing by hand when the service fails."""
        with mock.patch(GEOCODING_GET, side_effect=requests.ConnectionError("down")):
            response = self.htmx_get(self.url, {"address_line": "12 rue de la paix"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-address-suggestion")

    def test_anonymous_htmx_request_is_a_401(self):
        """An anonymous HTMX request gets a 401 with a redirect header."""
        self.client.logout()
        response = self.htmx_get(self.url, {"address_line": "12 rue de la paix"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("HX-Redirect", response)

    def test_post_is_not_allowed(self):
        """The view only answers GET."""
        self.assertEqual(self.htmx_post(self.url).status_code, 405)


@override_settings(GEOCODING_ENABLED=True)
class CertificationInFormsTests(HtmxClientMixin, TestCase):
    """Saving a folder or a profile address certifies it, without trusting the form."""

    def setUp(self):
        """Install the fake geocoder."""
        super().setUp()
        patcher = mock.patch(GEOCODING_GET, new=geo_router())
        self.router = patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_folder_is_certified(self):
        """The site address of a new folder is geocoded when it is created."""
        company = CompanyFactory(created_by=self.owner)
        self.htmx_post(
            reverse("inspections:create_folder"),
            {
                "company": company.pk,
                "address_line": "12 rue de la Paix",
                "postal_code": "75002",
                "city": "Paris",
                "latitude": "1",
                "longitude": "2",
            },
        )
        folder = InspectionFolder.objects.get()
        self.assertTrue(folder.address_certified)
        self.assertAlmostEqual(float(folder.latitude), 48.869141, places=5)

    def test_folder_without_address_calls_nothing(self):
        """The site address is optional: no address, no request."""
        company = CompanyFactory(created_by=self.owner)
        self.htmx_post(reverse("inspections:create_folder"), {"company": company.pk})
        self.assertTrue(InspectionFolder.objects.exists())
        self.router.assert_not_called()

    def test_edited_folder_is_certified_again(self):
        """Changing the site address replaces the coordinates of the old one."""
        folder = InspectionFolderFactory(created_by=self.owner)
        self.htmx_post(
            reverse("inspections:folder_inline_update", args=[folder.pk]),
            {
                "contact": "",
                "current_phase": folder.current_phase,
                "address_line": "12 rue de la Paix",
                "postal_code": "75002",
                "city": "Paris",
            },
        )
        folder.refresh_from_db()
        self.assertTrue(folder.address_certified)
        self.assertEqual(folder.geocoded_address, "12 rue de la Paix, 75002 Paris")

    def test_profile_address_is_certified(self):
        """The home address of the user is geocoded when saved."""
        self.htmx_post(
            reverse("accounts:profile_address"),
            {
                "address_line": "12 rue de la Paix",
                "postal_code": "75002",
                "city": "Paris",
            },
        )
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.address_certified)
        self.assertTrue(self.owner.has_coordinates)

    def test_profile_address_change_drops_the_old_position(self):
        """A new home address is not left with the coordinates of the old one."""
        self.htmx_post(
            reverse("accounts:profile_address"),
            {
                "address_line": "12 rue de la Paix",
                "postal_code": "75002",
                "city": "Paris",
            },
        )
        with mock.patch(GEOCODING_GET, new=geo_router(search=geo_response(503, {}))):
            self.htmx_post(
                reverse("accounts:profile_address"),
                {"address_line": "5 rue X", "postal_code": "69001", "city": "Lyon"},
            )
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.address_certified)
        self.assertIsNone(self.owner.latitude)

    def test_other_users_are_untouched(self):
        """Certifying one user never writes another one."""
        self.htmx_post(
            reverse("accounts:profile_address"),
            {
                "address_line": "12 rue de la Paix",
                "postal_code": "75002",
                "city": "Paris",
            },
        )
        other = UserFactory()
        self.assertFalse(other.address_certified)
