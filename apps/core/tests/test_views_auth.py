"""Tests for authentication and session views (accounts, core).

Every application URL is enumerated from the URL configuration, so a route added
later without protection is caught here. The public routes are listed explicitly in
``PUBLIC_ROUTES``.
"""

import unittest

from accounts.tests.factories import UserFactory
from django.conf import settings
from django.test import TestCase
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLPattern, URLResolver

APP_NAMESPACES = {"core", "crm", "inspections", "medias"}
PUBLIC_ROUTES = {"core:toggle_theme"}
"""Routes open to anonymous users on purpose (the theme only lives in the session)."""
HTMX_401_ROUTES = {
    "core:session_ping",
    "inspections:visit_form_section",
    "inspections:visit_save_answers",
}
"""Routes protected by ``htmx_login_required`` (401 for an anonymous HTMX request)."""
NEEDS_STRING_ARG = {"section_id": "s_general"}


def application_routes():
    """List every named route of the application namespaces.

    Returns:
        A sorted list of ``(full name, url)`` pairs. Each URL is built with the
        primary key 1 (and a section id when needed): anonymous requests are stopped
        before any lookup, so the objects do not have to exist.
    """
    routes = []

    def walk(patterns, namespace=""):
        """Collect the patterns, following the included URLconfs."""
        for entry in patterns:
            if isinstance(entry, URLResolver):
                inner = entry.namespace or ""
                walk(entry.url_patterns, inner or namespace)
            elif (
                isinstance(entry, URLPattern)
                and entry.name
                and namespace in APP_NAMESPACES
            ):
                converters = entry.pattern.converters
                kwargs = {arg: NEEDS_STRING_ARG.get(arg, 1) for arg in converters}
                routes.append(
                    (
                        f"{namespace}:{entry.name}",
                        reverse(f"{namespace}:{entry.name}", kwargs=kwargs),
                    )
                )

    walk(get_resolver().url_patterns)
    return sorted(set(routes))


class AnonymousAccessTests(TestCase):
    """What an anonymous visitor gets on every protected URL."""

    def protected_routes(self):
        """Return the routes that require a login.

        Returns:
            The ``(name, url)`` pairs of the application, public routes excluded.
        """
        return [(n, u) for n, u in application_routes() if n not in PUBLIC_ROUTES]

    def test_routes_were_found(self):
        """The enumeration is not empty (guards the tests below from passing for nothing)."""
        names = {name for name, _ in application_routes()}
        self.assertGreater(len(names), 60)
        self.assertIn("inspections:folder_detail", names)
        self.assertIn("medias:media_file", names)
        self.assertIn("crm:company_detail", names)

    def test_anonymous_is_redirected_to_login(self):
        """Every protected URL redirects an anonymous visitor to the login page, GET and POST."""
        login = reverse(settings.LOGIN_URL)
        for name, url in self.protected_routes():
            for method in ("GET", "POST"):
                with self.subTest(url=name, method=method):
                    response = self.client.generic(method, url)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response["Location"].startswith(f"{login}?next="))

    def test_anonymous_htmx_gets_401_on_htmx_login_required_routes(self):
        """The routes using ``htmx_login_required`` answer 401, without ``HX-Redirect``."""
        for name in sorted(HTMX_401_ROUTES):
            url = dict(application_routes())[name]
            method = "POST" if name == "inspections:visit_save_answers" else "GET"
            with self.subTest(url=name):
                response = self.client.generic(method, url, HTTP_HX_REQUEST="true")
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("HX-Redirect", response)

    @unittest.expectedFailure
    def test_known_gap_anonymous_htmx_gets_401_with_redirect_everywhere(self):
        """Known gap: only three views use ``htmx_login_required``; the others answer 302.

        An expired session on any HTMX request should get a 401 with ``HX-Redirect``
        (otherwise HTMX swaps the login page into the current page). Remove the
        ``expectedFailure`` mark once the decorator is applied to all HTMX views.
        """
        for name, url in self.protected_routes():
            if name in HTMX_401_ROUTES:
                continue
            with self.subTest(url=name):
                response = self.client.get(url, HTTP_HX_REQUEST="true")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["HX-Redirect"], reverse(settings.LOGIN_URL))

    def test_public_routes_stay_reachable(self):
        """The theme toggle works without login (it only writes to the session)."""
        response = self.client.get(reverse("core:toggle_theme"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["theme"], "light")

    def test_login_page_is_public(self):
        """The login page is reachable without login."""
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)


class LoginLogoutTests(TestCase):
    """Login and logout views."""

    def setUp(self):
        """Create a user with the factory password."""
        self.user = UserFactory()

    def test_valid_login_redirects_to_the_dashboard(self):
        """A valid login opens a session and goes to the dashboard."""
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": "password"},
        )
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_follows_next(self):
        """The ``next`` parameter set by ``login_required`` is honoured."""
        url = reverse("accounts:login") + "?next=" + reverse("inspections:folder_list")
        response = self.client.post(
            url, {"username": self.user.username, "password": "password"}
        )
        self.assertRedirects(response, reverse("inspections:folder_list"))

    def test_wrong_password_shows_the_error(self):
        """A wrong password re-renders the page with the error, without session."""
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identifiant ou mot de passe incorrect")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_ends_the_session(self):
        """A POST on logout flushes the session and goes back to the login page."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_logout_refuses_get(self):
        """Logging out needs a POST (no logout by a simple link or image)."""
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)


class SessionTests(TestCase):
    """``session_ping`` and the session settings."""

    def setUp(self):
        """Log a user in."""
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_ping_answers_204(self):
        """The heartbeat answers an empty 204."""
        response = self.client.get(reverse("core:session_ping"))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

    def test_ping_refreshes_the_session_cookie(self):
        """Every ping sends the session cookie again, which restarts the countdown."""
        response = self.client.get(reverse("core:session_ping"))
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(
            self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE
        )

    def test_session_settings(self):
        """One hour of inactivity, restarted by every request."""
        self.assertEqual(settings.SESSION_COOKIE_AGE, 3600)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_ping_rejects_other_methods(self):
        """Only GET is accepted."""
        self.assertEqual(
            self.client.post(reverse("core:session_ping")).status_code, 405
        )

    def test_anonymous_ping_does_not_create_a_user_session(self):
        """After logout the ping answers 401, so the form can warn the inspector."""
        self.client.logout()
        response = self.client.get(reverse("core:session_ping"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)


class ThemeTests(TestCase):
    """``toggle_theme`` and the ``theme_processor`` context processor."""

    def setUp(self):
        """Log a user in."""
        self.client.force_login(UserFactory())

    def test_default_theme_is_dark(self):
        """Without choice, the context says ``dark``."""
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["current_theme"], "dark")

    def test_toggle_switches_between_dark_and_light(self):
        """Each toggle flips the theme stored in the session."""
        self.client.get(reverse("core:toggle_theme"))
        self.assertEqual(self.client.session["theme"], "light")
        self.client.get(reverse("core:toggle_theme"))
        self.assertEqual(self.client.session["theme"], "dark")

    def test_context_follows_the_session(self):
        """After a toggle the templates receive the new theme."""
        self.client.get(reverse("core:toggle_theme"))
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["current_theme"], "light")

    def test_toggle_redirects_to_the_referer(self):
        """A classic request goes back to the page it came from."""
        response = self.client.get(
            reverse("core:toggle_theme"), HTTP_REFERER="/dossiers/"
        )
        self.assertRedirects(response, "/dossiers/", fetch_redirect_response=False)

    def test_toggle_without_referer_goes_home(self):
        """Without referer the redirect goes to the site root."""
        response = self.client.get(reverse("core:toggle_theme"))
        self.assertEqual(response["Location"], "/")

    def test_htmx_toggle_asks_for_a_refresh(self):
        """An HTMX request gets ``HX-Refresh`` instead of a redirect."""
        response = self.client.get(reverse("core:toggle_theme"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        self.assertEqual(self.client.session["theme"], "light")
