"""Tests of the stored travel estimate: service and view (computed only on request)."""

from unittest import mock

import requests
from accounts.tests.factories import UserFactory
from core.tests.helpers import (
    GEOCODING_GET,
    HtmxClientMixin,
    geo_response,
    geo_router,
    load_geo_fixture,
    make_certified,
)
from django.test import TestCase, override_settings
from django.urls import reverse

from inspections.models import InspectionFolder
from inspections.services.travel import (
    TravelError,
    is_travel_estimate_stale,
    refresh_travel_estimate,
)
from inspections.tests.factories import InspectionFolderFactory

TEMPLATE = "inspections/partials/folder/folder_travel.html"


class TravelTestCase(TestCase):
    """Base class: geocoding on, a certified user and a certified folder."""

    def setUp(self):
        """Create the certified home and site, and turn the geo services on."""
        super().setUp()
        override = override_settings(GEOCODING_ENABLED=True)
        override.enable()
        self.addCleanup(override.disable)
        self.user = make_certified(
            UserFactory(address_line="1 Rue A", postal_code="80000", city="Amiens"),
            "49.897442",
            "2.290084",
        )
        self.folder = make_certified(
            InspectionFolderFactory(
                created_by=self.user,
                address_line="12 Rue de la Paix",
                postal_code="75002",
                city="Paris",
            )
        )

    def network(self, **kwargs):
        """Install the fake geo network for the rest of the test.

        Args:
            **kwargs: Passed to ``geo_router``.

        Returns:
            The mock replacing ``requests.get``.
        """
        patcher = mock.patch(GEOCODING_GET, new=geo_router(**kwargs))
        router = patcher.start()
        self.addCleanup(patcher.stop)
        return router

    def reload(self):
        """Return the folder as stored in the database."""
        return InspectionFolder.objects.get(pk=self.folder.pk)


class RefreshTravelEstimateTests(TravelTestCase):
    """``refresh_travel_estimate`` computes and stores the trip."""

    def test_trip_from_home_is_stored(self):
        """The default starting point is the home of the user."""
        self.network()
        refresh_travel_estimate(self.folder, self.user)
        folder = self.reload()
        self.assertEqual((folder.travel_minutes, str(folder.travel_km)), (120, "143.4"))
        self.assertEqual(folder.travel_origin_kind, "home")
        self.assertEqual(folder.travel_origin_label, "1 Rue A, 80000 Amiens")
        self.assertEqual(folder.travel_destination_label, folder.full_address)
        self.assertIsNotNone(folder.travel_computed_at)

    def test_custom_origin_is_geocoded_and_remembered(self):
        """Another starting point is geocoded then reused by the next computation."""
        router = self.network()
        refresh_travel_estimate(
            self.folder, self.user, origin_address="12 rue de la paix paris"
        )
        folder = self.reload()
        self.assertEqual(folder.travel_origin_kind, "custom")
        self.assertEqual(folder.travel_origin_label, "12 Rue de la Paix, 75002 Paris")
        calls = router.call_count
        refresh_travel_estimate(folder, self.user)
        # The second computation asks the route only: the custom point is not geocoded again
        self.assertEqual(router.call_count, calls + 1)
        self.assertEqual(self.reload().travel_origin_kind, "custom")

    def test_use_home_goes_back_to_the_home(self):
        """``use_home`` replaces a custom starting point by the home."""
        self.network()
        refresh_travel_estimate(
            self.folder, self.user, origin_address="12 rue de la paix paris"
        )
        refresh_travel_estimate(self.reload(), self.user, use_home=True)
        self.assertEqual(self.reload().travel_origin_kind, "home")

    def test_unknown_custom_origin_is_refused(self):
        """A starting point the geocoder does not find gives an error and no change."""
        self.network(
            search=geo_response(200, load_geo_fixture("geopf_search_empty.json"))
        )
        with self.assertRaisesMessage(TravelError, "introuvable"):
            refresh_travel_estimate(self.folder, self.user, origin_address="zzzz")
        self.assertIsNone(self.reload().travel_computed_at)

    def test_site_must_be_certified(self):
        """An uncertified site address gives an error without calling any service."""
        folder = InspectionFolderFactory(created_by=self.user)
        router = self.network()
        with self.assertRaisesMessage(TravelError, "n'est pas certifiée"):
            refresh_travel_estimate(folder, self.user)
        router.assert_not_called()

    def test_home_must_be_certified(self):
        """Without a certified home the user is asked to complete the profile."""
        user = UserFactory()
        folder = make_certified(InspectionFolderFactory(created_by=user))
        router = self.network()
        with self.assertRaisesMessage(TravelError, "profil"):
            refresh_travel_estimate(folder, user)
        router.assert_not_called()

    def test_failure_keeps_the_previous_estimate(self):
        """A route service failure never erases the stored estimate."""
        self.network()
        refresh_travel_estimate(self.folder, self.user)
        before = self.reload()
        self.network(route=requests.ConnectionError("down"))
        with self.assertRaisesMessage(TravelError, "indisponible"):
            refresh_travel_estimate(before, self.user)
        after = self.reload()
        self.assertEqual(
            (after.travel_minutes, after.travel_computed_at),
            (before.travel_minutes, before.travel_computed_at),
        )

    def test_no_road_has_its_own_message(self):
        """A missing road is reported as such, not as a service failure."""
        self.network(route=geo_response(404, {"error": {"message": "No path found"}}))
        with self.assertRaisesMessage(TravelError, "Aucun itinéraire"):
            refresh_travel_estimate(self.folder, self.user)


class StaleEstimateTests(TravelTestCase):
    """The estimate is marked stale, never recomputed by itself."""

    def setUp(self):
        """Store an estimate first."""
        super().setUp()
        self.network()
        refresh_travel_estimate(self.folder, self.user)
        self.folder = self.reload()

    def test_fresh_estimate_is_not_stale(self):
        """Nothing changed since the computation."""
        self.assertFalse(is_travel_estimate_stale(self.folder, self.user))

    def test_no_estimate_is_not_stale(self):
        """A folder without estimate has nothing to recompute."""
        folder = InspectionFolderFactory(created_by=self.user)
        self.assertFalse(is_travel_estimate_stale(folder, self.user))

    def test_new_site_address_makes_it_stale(self):
        """Editing the site address flags the estimate without calling any service."""
        router = self.network()
        calls = router.call_count
        self.folder.city = "Lyon"
        self.folder.save()
        self.assertTrue(is_travel_estimate_stale(self.folder, self.user))
        self.assertEqual(router.call_count, calls)

    def test_new_home_address_makes_a_home_trip_stale(self):
        """Moving house flags a trip that started from home."""
        self.user.city = "Lille"
        self.assertTrue(is_travel_estimate_stale(self.folder, self.user))

    def test_new_home_address_does_not_touch_a_custom_trip(self):
        """A trip from another point does not depend on the home address."""
        refresh_travel_estimate(
            self.folder, self.user, origin_address="12 rue de la paix paris"
        )
        folder = self.reload()
        self.user.city = "Lille"
        self.assertFalse(is_travel_estimate_stale(folder, self.user))


class FolderTravelViewTests(HtmxClientMixin, TravelTestCase):
    """The ``folder_travel`` view and the tabs that display the estimate."""

    def setUp(self):
        """Log the certified user in."""
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("inspections:folder_travel", args=[self.folder.pk])

    def test_post_computes_and_renders_the_card(self):
        """A POST stores the trip and shows it."""
        self.network()
        response = self.htmx_post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertContains(response, "120 min")
        self.assertEqual(self.reload().travel_minutes, 120)

    def test_error_is_a_422_with_the_message(self):
        """A failure re-renders the card with the message and a 422."""
        self.network(route=requests.ConnectionError("down"))
        response = self.htmx_post(self.url)
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "indisponible", status_code=422)
        self.assertIsNone(self.reload().travel_computed_at)

    def test_custom_origin_is_posted(self):
        """The ``origin_address`` field starts the trip from another point."""
        self.network()
        self.htmx_post(self.url, {"origin_address": "12 rue de la paix paris"})
        self.assertEqual(self.reload().travel_origin_kind, "custom")

    def test_overview_never_calls_the_services(self):
        """Displaying the folder uses the stored estimate: no network call."""
        self.network()
        self.htmx_post(self.url)
        router = self.network()
        for name in ("folder_tab_overview", "folder_detail"):
            response = self.client.get(
                reverse(f"inspections:{name}", args=[self.folder.pk])
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "120 min")
        router.assert_not_called()

    def test_stale_estimate_is_flagged_on_the_page(self):
        """A trip computed for another address is shown as « À recalculer »."""
        self.network()
        self.htmx_post(self.url)
        folder = self.reload()
        folder.city = "Lyon"
        folder.save()
        response = self.client.get(
            reverse("inspections:folder_tab_overview", args=[folder.pk])
        )
        self.assertContains(response, "À recalculer")

    def test_other_user_gets_404(self):
        """Another user cannot compute the trip of a folder."""
        self.client.force_login(UserFactory())
        router = self.network()
        self.assertEqual(self.htmx_post(self.url).status_code, 404)
        router.assert_not_called()

    def test_get_is_not_allowed(self):
        """The computation is a POST only."""
        self.assertEqual(self.htmx_get(self.url).status_code, 405)

    def test_anonymous_htmx_request_is_a_401(self):
        """An anonymous HTMX request gets a 401 with a redirect header."""
        self.client.logout()
        response = self.htmx_post(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertIn("HX-Redirect", response)

    def test_archived_folder_is_a_409(self):
        """An archived folder is read only."""
        self.folder.archive(self.user)
        router = self.network()
        self.assertEqual(self.htmx_post(self.url).status_code, 409)
        router.assert_not_called()
