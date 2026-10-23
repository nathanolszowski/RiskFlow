"""Helpers shared by the view tests of every app."""

import json
from collections import namedtuple
from pathlib import Path
from unittest import mock

import requests
from accounts.tests.factories import UserFactory
from django.urls import reverse
from django.utils import timezone

Route = namedtuple("Route", "name key methods")
"""A URL under test: its name, the name of its primary key argument and its methods."""

GET, POST, BOTH = ("GET",), ("POST",), ("GET", "POST")


class HtmxClientMixin:
    """Add two users, a logged-in client and HTMX request shortcuts to a test case.

    Put it before ``TestCase`` in the bases. ``setUp`` creates ``owner`` (logged in
    with ``force_login``) and ``other`` (not logged in). Log in as someone else with
    ``self.client.force_login(self.other)``.

    Attributes:
        owner: User who owns the objects the test creates, logged in on ``client``.
        other: Second user, who must never reach the objects of ``owner``.
    """

    def setUp(self):
        """Create the two users and log the owner in."""
        super().setUp()
        self.owner = UserFactory()
        self.other = UserFactory()
        self.client.force_login(self.owner)

    def htmx_get(self, url, data=None, **extra):
        """Send a GET request flagged as HTMX.

        Args:
            url: URL to request.
            data: Query string parameters.
            **extra: Extra WSGI/headers arguments passed to the test client
                (e.g. ``HTTP_HX_TARGET="#tab-content"``).

        Returns:
            The response.
        """
        return self.client.get(url, data or {}, HTTP_HX_REQUEST="true", **extra)

    def htmx_post(self, url, data=None, **extra):
        """Send a POST request flagged as HTMX.

        Args:
            url: URL to request.
            data: Posted form data.
            **extra: Extra WSGI/headers arguments passed to the test client.

        Returns:
            The response.
        """
        return self.client.post(url, data or {}, HTTP_HX_REQUEST="true", **extra)


class IsolationMixin:
    """Check that a user gets a 404 on every URL of an object owned by someone else.

    The test case must define ``database_state()`` returning a comparable snapshot of
    the tables the URLs could change.
    """

    def check_routes_404(self, routes, obj, extra_kwargs=None):
        """Request each route and expect a 404, with no change in the database.

        The request is made by the user currently logged in on ``self.client``, who
        must not own ``obj``. For a route that only allows one method, the other
        method is expected to be refused with a 405 before anything is looked up.

        Args:
            routes: ``Route`` items of one kind of object.
            obj: Object owned by someone else that the routes point to.
            extra_kwargs: Additional URL arguments, if any.
        """
        for route in routes:
            url = reverse(
                route.name, kwargs={route.key: obj.pk, **(extra_kwargs or {})}
            )
            for method in route.methods:
                with self.subTest(url=route.name, method=method):
                    before = self.database_state()
                    response = self.client.generic(method, url)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(self.database_state(), before)
            if len(route.methods) == 1:
                other_method = "POST" if route.methods == GET else "GET"
                with self.subTest(url=route.name, method=other_method):
                    response = self.client.generic(other_method, url)
                    self.assertEqual(response.status_code, 405)


GEOCODING_GET = "core.services.geo.geocoding.requests.get"
"""``requests.get`` as seen by the geocoder (one attribute of the ``requests`` module)."""

GEO_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_geo_fixture(name):
    """Read a JSON fixture of ``core/tests/fixtures/``.

    Args:
        name: File name, e.g. ``geopf_search_housenumber.json``.

    Returns:
        The decoded content, a new object on each call.
    """
    return json.loads((GEO_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def geo_response(status=200, payload=None):
    """Build a fake ``requests`` response for the Géoplateforme.

    Args:
        status: HTTP status code.
        payload: Value returned by ``response.json()``; an exception instance is raised.

    Returns:
        A mock with ``status_code`` and ``json()``.
    """
    response = mock.Mock(spec=requests.Response)
    response.status_code = status
    if isinstance(payload, Exception):
        response.json.side_effect = payload
    else:
        response.json.return_value = payload
    return response


def make_certified(obj, latitude="48.869141", longitude="2.331303"):
    """Give a saved model with ``AddressMixin`` certified coordinates, with no network.

    The coordinates are written with a queryset update: ``save()`` would drop them,
    as the address text no longer matches what was geocoded.

    Args:
        obj: Saved instance with an address.
        latitude: Latitude to store.
        longitude: Longitude to store.

    Returns:
        The refreshed instance.
    """
    type(obj).objects.filter(pk=obj.pk).update(
        latitude=latitude,
        longitude=longitude,
        address_certified=True,
        geocoded_at=timezone.now(),
        geocoded_address=obj.full_address,
    )
    obj.refresh_from_db()
    return obj


def geo_router(search=None, route=None):
    """Build a ``requests.get`` replacement answering the geocoder and the route service.

    Both services call ``requests.get`` (one attribute of the ``requests`` module), so
    one fake serves them by URL.

    Args:
        search: Response for ``/search``. Default: the house number fixture.
        route: Response (or exception to raise) for the route service. Default: the
            route fixture (120 min, 143.4 km).

    Returns:
        A mock usable with ``mock.patch(GEOCODING_GET, new=...)``.
    """
    if search is None:
        search = geo_response(200, load_geo_fixture("geopf_search_housenumber.json"))
    if route is None:
        route = geo_response(200, load_geo_fixture("geopf_route.json"))

    def fake_get(url, *args, **kwargs):
        """Answer with the response registered for the service."""
        answer = route if "itineraire" in url else search
        if isinstance(answer, Exception):
            raise answer
        return answer

    return mock.Mock(side_effect=fake_get)
