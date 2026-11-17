"""Tests for ``core/text.py`` (wording), ``core/http.py`` (filters) and ``core/htmx.py``."""

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from core.htmx import close_modal, htmx_redirect, htmx_refresh, retarget_modal
from core.http import filter_params
from core.text import agree, plural


class WordingTests(SimpleTestCase):
    """``agree`` and ``plural``."""

    def test_agree_uses_the_singular_up_to_one(self):
        """0 and 1 take the singular, 2 and more the plural (``s`` by default)."""
        self.assertEqual(
            [agree(n, "actif") for n in (0, 1, 2)], ["actif", "actif", "actifs"]
        )
        self.assertEqual(agree(3, "est lié", "sont liés"), "sont liés")

    def test_plural_prefixes_the_quantity(self):
        """The quantity comes first, the word agrees with it."""
        self.assertEqual(plural(1, "visite"), "1 visite")
        self.assertEqual(plural(4, "média"), "4 médias")


class FilterParamsTests(SimpleTestCase):
    """``filter_params``."""

    def test_only_present_parameters_are_returned_stripped(self):
        """Missing filters are left out, present ones (even empty) are stripped."""
        request = RequestFactory().get("/", {"q": "  acme ", "status": ""})
        self.assertEqual(
            filter_params(request, "q", "status", "sort"), {"q": "acme", "status": ""}
        )

    def test_post_is_read_only_when_asked(self):
        """POST data counts with ``include_post``, a non-empty GET value winning."""
        request = RequestFactory().post("/?q=get", {"q": "post", "phase": "VISIT"})
        self.assertEqual(filter_params(request, "q", "phase"), {"q": "get"})
        self.assertEqual(
            filter_params(request, "q", "phase", include_post=True),
            {"q": "get", "phase": "VISIT"},
        )


class HtmxResponsesTests(SimpleTestCase):
    """``core/htmx.py``: the headers read by HTMX."""

    def test_refresh_and_redirect(self):
        """``htmx_refresh`` and ``htmx_redirect`` set their header and status."""
        refresh = htmx_refresh(status=204)
        self.assertEqual((refresh.status_code, refresh["HX-Refresh"]), (204, "true"))
        redirect = htmx_redirect("/dossiers/")
        self.assertEqual(
            (redirect.status_code, redirect["HX-Redirect"]), (200, "/dossiers/")
        )

    def test_close_and_retarget_modal(self):
        """The modal helpers add their headers to the given response."""
        response = close_modal(HttpResponse("grid"))
        self.assertEqual(response["HX-Trigger"], "closeModal")
        response = retarget_modal(HttpResponse("modal", status=422))
        self.assertEqual(
            (response["HX-Retarget"], response["HX-Reswap"]),
            ("#modal-container", "innerHTML"),
        )
