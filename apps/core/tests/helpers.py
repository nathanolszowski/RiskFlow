"""Helpers shared by the view tests of every app."""

from collections import namedtuple

from accounts.tests.factories import UserFactory
from django.urls import reverse

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
