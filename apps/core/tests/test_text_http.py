"""Tests for the wording helpers (``core/text.py``) and the filter reading (``core/http.py``)."""

from django.test import RequestFactory, SimpleTestCase

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
