"""Helpers of the crm tests: Sirene fixtures and fake HTTP responses."""

import json
from pathlib import Path
from unittest import mock

import requests

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

SIRET_SIEGE = "12345678200010"
SIRET_SECONDAIRE = "12345678200028"

GET_COMPANY = "crm.services.company.requests.get"
GET_NAF = GET_COMPANY  # same attribute (requests.get): see sirene_router


def load_fixture(name):
    """Read a JSON (or JSON-LD) fixture of ``crm/tests/fixtures/``.

    Args:
        name: File name, e.g. ``etab_siege_actif.json``.

    Returns:
        The decoded content. Each call returns a new object, safe to modify.
    """
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def fake_response(status=200, payload=None):
    """Build a fake ``requests`` response.

    Args:
        status: HTTP status code.
        payload: Value returned by ``response.json()``. If it is an exception
            instance, ``json()`` raises it (use ``ValueError`` for a non-JSON body).

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


def sirene_router(routes, naf=None):
    """Build a ``requests.get`` replacement answering Sirene and NAF requests.

    The Sirene client and the NAF service both call ``requests.get``, which is one
    single attribute of the ``requests`` module: patching it twice would make the
    second patch hide the first. One fake therefore serves both, by URL.

    Args:
        routes: Mapping ``{siret: response}`` for the Sirene API. A SIRET that is not
            listed gets a 404.
        naf: Response (or exception to raise) for the NAF label service. By default
            the label fixture is served.

    Returns:
        A mock usable with ``mock.patch(GET_COMPANY, new=...)``. Its ``call_args_list``
        records every URL asked, see ``sirene_urls`` and ``naf_urls``.
    """
    if naf is None:
        naf = fake_response(200, load_fixture("naf25_label.jsonld"))

    def fake_get(url, *args, **kwargs):
        """Answer with the response registered for the URL."""
        if "id.insee.fr" in url:
            if isinstance(naf, Exception) or (
                isinstance(naf, type) and issubclass(naf, Exception)
            ):
                raise naf
            return naf
        return routes.get(url.rsplit("/", 1)[-1], fake_response(404, {}))

    return mock.Mock(side_effect=fake_get)


def _urls(router, marker):
    """Return the URLs asked to a fake network that contain a marker.

    Args:
        router: Mock returned by ``sirene_router``.
        marker: Text looked for in the URL.

    Returns:
        The URLs, in call order.
    """
    return [c.args[0] for c in router.call_args_list if marker in c.args[0]]


def sirene_urls(router):
    """Return the URLs asked to the Sirene API.

    Args:
        router: Mock returned by ``sirene_router``.

    Returns:
        The URLs, in call order.
    """
    return _urls(router, "api.insee.fr")


def naf_urls(router):
    """Return the URLs asked to the NAF label service.

    Args:
        router: Mock returned by ``sirene_router``.

    Returns:
        The URLs, in call order.
    """
    return _urls(router, "id.insee.fr")
