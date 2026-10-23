"""Tests of the route service: travel time and distance between two points."""

from decimal import Decimal
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from core.services.geo import NoRouteFound, RoutingUnavailable, get_travel_time

from .helpers import GEOCODING_GET, geo_response, load_geo_fixture

ORIGIN = (Decimal("49.897442"), Decimal("2.290084"))
DESTINATION = (Decimal("48.8566"), Decimal("2.3522"))


@override_settings(GEOCODING_ENABLED=True)
class TravelTimeTests(SimpleTestCase):
    """``get_travel_time`` reads the duration and the distance of the fastest route."""

    def ask(self, response):
        """Call the service with a fake answer.

        Args:
            response: Fake response, or an exception to raise.

        Returns:
            ``(result, mock)`` where result is the travel and mock the fake ``get``.
        """
        with mock.patch(GEOCODING_GET) as get:
            if isinstance(response, Exception):
                get.side_effect = response
            else:
                get.return_value = response
            result = get_travel_time(ORIGIN, DESTINATION)
        return result, get

    def test_returns_minutes_and_kilometers(self):
        """The duration is rounded to the minute, the distance to 0.1 km."""
        result, _ = self.ask(geo_response(200, load_geo_fixture("geopf_route.json")))
        self.assertEqual(result.minutes, 120)
        self.assertEqual(result.kilometers, Decimal("143.4"))

    def test_sends_longitude_first_and_the_car_profile(self):
        """Points are sent as ``lon,lat``, for a fastest car route."""
        _, get = self.ask(geo_response(200, load_geo_fixture("geopf_route.json")))
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["start"], "2.290084,49.897442")
        self.assertEqual(params["end"], "2.3522,48.8566")
        self.assertEqual(
            (params["profile"], params["optimization"]), ("car", "fastest")
        )
        self.assertEqual(
            (params["timeUnit"], params["distanceUnit"]), ("minute", "kilometer")
        )

    def test_a_very_short_trip_lasts_at_least_one_minute(self):
        """A duration below 30 seconds is not shown as 0 minutes."""
        payload = {"duration": 0.2, "distance": 0.04}
        result, _ = self.ask(geo_response(200, payload))
        self.assertEqual(result.minutes, 1)

    def test_no_road_raises_no_route_found(self):
        """The service answering ``No path found`` raises ``NoRouteFound``."""
        with self.assertRaises(NoRouteFound):
            self.ask(geo_response(404, {"error": {"message": "No path found"}}))

    def test_errors_raise_routing_unavailable(self):
        """Network errors, server errors and broken bodies raise ``RoutingUnavailable``."""
        for response in (
            requests.Timeout("slow"),
            geo_response(503, {}),
            geo_response(429, {}),
            geo_response(200, ValueError("not json")),
            geo_response(200, {"unexpected": 1}),
        ):
            with self.subTest(response=response):
                with self.assertRaises(RoutingUnavailable):
                    self.ask(response)

    @override_settings(GEOCODING_ENABLED=False)
    def test_disabled_service_is_unavailable(self):
        """With the geo services turned off nothing is called."""
        with mock.patch(GEOCODING_GET) as get:
            with self.assertRaises(RoutingUnavailable):
                get_travel_time(ORIGIN, DESTINATION)
        get.assert_not_called()
