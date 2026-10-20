"""Tests for ``htmx_login_required`` (core/decorators.py), through ``RequestFactory``."""

from accounts.tests.factories import UserFactory
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from core.decorators import htmx_login_required


def build_request(user, htmx=False):
    """Build a GET request for a given user.

    Args:
        user: User attached to the request (a real user or ``AnonymousUser``).
        htmx: Whether the request carries the ``HX-Request`` header.

    Returns:
        The request.
    """
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    request = RequestFactory().get("/some/page/?x=1", **extra)
    request.user = user
    return request


@htmx_login_required
def plain_view(request):
    """Return a 200 response (decorated without parentheses)."""
    return HttpResponse("ok")


@htmx_login_required()
def called_view(request):
    """Return a 200 response (decorated with empty parentheses)."""
    return HttpResponse("ok")


@htmx_login_required(redirect=False)
def silent_view(request):
    """Return a 200 response (decorated with ``redirect=False``)."""
    return HttpResponse("ok")


class HtmxLoginRequiredAnonymousTests(SimpleTestCase):
    """Behaviour for an anonymous visitor."""

    def test_htmx_request_gets_401_with_redirect_header(self):
        """An anonymous HTMX request gets 401 and an ``HX-Redirect`` to the login."""
        response = plain_view(build_request(AnonymousUser(), htmx=True))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["HX-Redirect"], reverse(settings.LOGIN_URL))

    def test_redirect_false_gets_401_without_header(self):
        """With ``redirect=False`` the 401 has no ``HX-Redirect`` header."""
        response = silent_view(build_request(AnonymousUser(), htmx=True))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("HX-Redirect", response)

    def test_classic_request_is_redirected_to_login_with_next(self):
        """An anonymous classic request is redirected to the login with ``next``."""
        response = plain_view(build_request(AnonymousUser()))
        self.assertEqual(response.status_code, 302)
        login = reverse(settings.LOGIN_URL)
        self.assertEqual(response["Location"], f"{login}?next=/some/page/%3Fx%3D1")

    def test_classic_request_ignores_redirect_false(self):
        """``redirect=False`` only concerns HTMX: classic requests still go to the login."""
        response = silent_view(build_request(AnonymousUser()))
        self.assertEqual(response.status_code, 302)

    def test_usable_with_and_without_parentheses(self):
        """Both decorator forms protect the view the same way."""
        for view in (plain_view, called_view):
            with self.subTest(view=view.__name__):
                response = view(build_request(AnonymousUser(), htmx=True))
                self.assertEqual(response.status_code, 401)

    def test_decorator_keeps_the_view_name(self):
        """``functools.wraps`` keeps the name and the docstring of the view."""
        self.assertEqual(plain_view.__name__, "plain_view")
        self.assertIn("200", plain_view.__doc__)


class HtmxLoginRequiredAuthenticatedTests(TestCase):
    """Behaviour for a logged-in user."""

    def test_authenticated_user_reaches_the_view(self):
        """A logged-in user, HTMX or not, gets the response of the view."""
        user = UserFactory()
        for view in (plain_view, called_view, silent_view):
            for htmx in (False, True):
                with self.subTest(view=view.__name__, htmx=htmx):
                    response = view(build_request(user, htmx=htmx))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, b"ok")
