"""Tests for the NAF 2025 labels (crm/services/naf.py).

``requests.get`` is patched: the INSEE nomenclature service is never reached.
"""

from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from crm.services import naf
from crm.services.naf import fetch_naf25_label
from crm.tests.helpers import GET_NAF, fake_response, load_fixture

CODE = "62.01Z"


class FetchNafLabelTests(SimpleTestCase):
    """``fetch_naf25_label`` with a fake JSON-LD service."""

    def setUp(self):
        """Clear the cache so that tests do not see each other's labels."""
        super().setUp()
        cache.clear()

    def get(self, response=None, **kwargs):
        """Patch ``requests.get`` for the duration of the test.

        Args:
            response: Response returned by the fake service (the label fixture by default).
            **kwargs: Extra arguments of ``mock.patch`` (e.g. ``side_effect``).

        Returns:
            The patched ``requests.get`` mock.
        """
        if response is None and "side_effect" not in kwargs:
            response = fake_response(200, load_fixture("naf25_label.jsonld"))
        patcher = mock.patch(GET_NAF, return_value=response, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def test_label_is_read_from_the_json_ld(self):
        """The French ``prefLabel`` of the code is returned (not the English one)."""
        self.get()
        self.assertEqual(fetch_naf25_label(CODE), "Programmation informatique")

    def test_request_url_and_headers(self):
        """The code is put in the id.insee.fr URL and JSON-LD is requested."""
        mocked = self.get()
        fetch_naf25_label(CODE)
        self.assertEqual(
            mocked.call_args.args[0],
            "https://id.insee.fr/codes/naf2025/sousClasse/62.01Z",
        )
        self.assertEqual(
            mocked.call_args.kwargs["headers"], {"Accept": "application/ld+json"}
        )
        self.assertEqual(mocked.call_args.kwargs["timeout"], 5)

    def test_label_is_cached(self):
        """A second call is served by the cache, without request."""
        mocked = self.get()
        fetch_naf25_label(CODE)
        self.assertEqual(fetch_naf25_label(CODE), "Programmation informatique")
        self.assertEqual(mocked.call_count, 1)

    def test_known_label_uses_the_long_cache_duration(self):
        """A known label is kept for ``LABEL_CACHE_SECONDS``."""
        self.get()
        with mock.patch.object(naf, "cache") as fake_cache:
            fake_cache.get.return_value = None
            fetch_naf25_label(CODE)
        fake_cache.set.assert_called_once_with(
            f"naf25-label-{CODE}", "Programmation informatique", naf.LABEL_CACHE_SECONDS
        )

    def test_unknown_code_is_cached_for_a_shorter_time(self):
        """A code without label is remembered, for ``UNKNOWN_CACHE_SECONDS`` only."""
        mocked = self.get()
        with mock.patch.object(naf, "cache") as fake_cache:
            fake_cache.get.return_value = None
            self.assertEqual(fetch_naf25_label("99.99Z"), "")
        fake_cache.set.assert_called_once_with(
            "naf25-label-99.99Z", "", naf.UNKNOWN_CACHE_SECONDS
        )
        self.assertLess(naf.UNKNOWN_CACHE_SECONDS, naf.LABEL_CACHE_SECONDS)
        mocked.reset_mock()
        fetch_naf25_label("99.99Z")
        fetch_naf25_label("99.99Z")
        self.assertEqual(mocked.call_count, 1)

    def test_invalid_codes_make_no_request(self):
        """A value that is not a NAF 2025 code is refused before it reaches the URL."""
        mocked = self.get()
        for code in (
            "",
            None,
            "62.01",
            "6201Z",
            "62.01z",
            "../etc/passwd",
            "62.01Z/x",
            " ",
        ):
            with self.subTest(code=code):
                self.assertEqual(fetch_naf25_label(code), "")
        mocked.assert_not_called()

    def test_code_is_stripped(self):
        """Spaces around the code are ignored."""
        self.get()
        self.assertEqual(fetch_naf25_label(f" {CODE} "), "Programmation informatique")

    def test_network_errors_give_an_empty_label_and_are_not_cached(self):
        """A network error returns ``""`` and the next call tries again."""
        for error in (requests.Timeout, requests.ConnectionError):
            with self.subTest(error=error.__name__):
                cache.clear()
                mocked = self.get(side_effect=error)
                self.assertEqual(fetch_naf25_label(CODE), "")
                self.assertEqual(fetch_naf25_label(CODE), "")
                self.assertEqual(mocked.call_count, 2)

    def test_error_status_gives_an_empty_label_and_is_not_cached(self):
        """A non-200 answer returns ``""`` without being cached."""
        mocked = self.get(fake_response(503, {}))
        self.assertEqual(fetch_naf25_label(CODE), "")
        fetch_naf25_label(CODE)
        self.assertEqual(mocked.call_count, 2)

    def test_unreadable_body_gives_an_empty_label(self):
        """A body that is not JSON gives ``""``."""
        self.get(fake_response(200, ValueError("no json")))
        self.assertEqual(fetch_naf25_label(CODE), "")

    def test_unexpected_json_shapes_give_an_empty_label(self):
        """Anything other than the expected list of nodes gives ``""``."""
        payloads = [
            {"not": "a list"},
            [],
            [{"@id": "http://id.insee.fr/codes/naf2025/sousClasse/62.01Z"}],
            [
                {
                    "@id": "http://id.insee.fr/codes/naf2025/sousClasse/62.01Z",
                    naf.PREF_LABEL: [{"@language": "en", "@value": "Only English"}],
                }
            ],
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                cache.clear()
                self.get(fake_response(200, payload))
                self.assertEqual(fetch_naf25_label(CODE), "")
