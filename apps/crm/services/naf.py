"""Label of a NAF 2025 activity code, read from the INSEE nomenclature service.

The Sirene API only returns the code (``activitePrincipaleNAF25UniteLegale``, e.g. ``58.29Y``).
The label comes from ``id.insee.fr``, the INSEE reference of the nomenclatures, which
answers JSON-LD (SKOS) without any key. Nothing is kept in the code: the label is read
once when a client is imported or updated, then stored on the client.
"""

import re

import requests
from django.core.cache import cache

NAF25_URL = "https://id.insee.fr/codes/naf2025/sousClasse/{code}"
# The identifiers inside the answer use http, whatever the scheme of the request
NAF25_ID = "http://id.insee.fr/codes/naf2025/sousClasse/{code}"
PREF_LABEL = "http://www.w3.org/2004/02/skos/core#prefLabel"
NAF25_CODE_PATTERN = re.compile(r"\d{2}\.\d{2}[A-Z]")

# A known label never changes within a nomenclature edition; an unknown code is retried daily
LABEL_CACHE_SECONDS = 30 * 24 * 3600
UNKNOWN_CACHE_SECONDS = 24 * 3600


def fetch_naf25_label(code: str) -> str:
    """Return the French label of a NAF 2025 sub-class code.

    Network errors are swallowed and not cached, so the next call tries again.

    Args:
        code: NAF 2025 code, e.g. ``58.29Y``. Anything else gives an empty label
            (the code is put in the URL, so it is checked first).

    Returns:
        The label (e.g. ``Édition d’autres logiciels``), or an empty string if the
        code is unknown or the service cannot be reached.
    """
    code = (code or "").strip()
    if not NAF25_CODE_PATTERN.fullmatch(code):
        return ""

    key = f"naf25-label-{code}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    url = NAF25_URL.format(code=code)
    try:
        response = requests.get(
            url, headers={"Accept": "application/ld+json"}, timeout=5
        )
        if response.status_code != 200:
            return ""
        nodes = response.json()
    except (requests.RequestException, ValueError):
        return ""

    label = ""
    node_id = NAF25_ID.format(code=code)
    for node in nodes if isinstance(nodes, list) else []:
        if node.get("@id") != node_id:
            continue
        for pref in node.get(PREF_LABEL, []):
            if pref.get("@language") == "fr":
                label = str(pref.get("@value", "")).strip()
    cache.set(key, label, LABEL_CACHE_SECONDS if label else UNKNOWN_CACHE_SECONDS)
    return label
