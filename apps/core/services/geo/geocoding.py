"""Geocoding of addresses with the Géoplateforme geocoder (BAN addresses, no API key).

``geocode`` finds one address, ``suggest`` feeds the address autocompletion and
``certify_address`` stores the coordinates of a model with ``AddressMixin``. The
coordinates are kept in the database: nothing is geocoded again until the address
changes or ``force=True`` is given.
"""

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.models import AddressMixin

REQUEST_TIMEOUT = 5
SUGGESTIONS_CACHE_SECONDS = 300
MIN_SUGGESTION_LENGTH = 3
# Result kinds precise enough to place an inspection (a municipality centre is not)
CERTIFIABLE_TYPES = ("housenumber", "street", "locality")


class GeocodingUnavailable(Exception):
    """The geocoding service could not be reached or answered with an error."""


@dataclass(frozen=True)
class GeocodeResult:
    """One address returned by the geocoder.

    Attributes:
        address_line: Number and street.
        postal_code: Postal code.
        city: City.
        citycode: INSEE code of the municipality.
        latitude: Latitude (WGS84).
        longitude: Longitude (WGS84).
        score: Relevance between 0 and 1.
        kind: ``housenumber``, ``street``, ``locality`` or ``municipality``.
        label: Full one-line label.
    """

    address_line: str
    postal_code: str
    city: str
    citycode: str
    latitude: Decimal
    longitude: Decimal
    score: float
    kind: str
    label: str

    @property
    def is_certifiable(self) -> bool:
        """Return whether the result is reliable and precise enough to certify."""
        return (
            self.score >= settings.GEOCODING_MIN_SCORE
            and self.kind in CERTIFIABLE_TYPES
        )


def _search(params: dict[str, Any]) -> list[GeocodeResult]:
    """Call ``/search`` and parse the features.

    Raises:
        GeocodingUnavailable: On a network error, an HTTP error or an unreadable answer.
    """
    if not settings.GEOCODING_ENABLED:
        raise GeocodingUnavailable("geocoding disabled")
    try:
        response = requests.get(
            f"{settings.GEOPF_GEOCODING_URL}/search",
            params={"index": "address", **params},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise GeocodingUnavailable(f"HTTP {response.status_code}")
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingUnavailable(str(exc)) from exc
    results = []
    for feature in features:
        result = _parse_feature(feature)
        if result:
            results.append(result)
    return results


def _parse_feature(feature: dict) -> GeocodeResult | None:
    """Turn a GeoJSON feature into a result, or None if it is incomplete."""
    props = feature.get("properties") or {}
    try:
        longitude, latitude = feature["geometry"]["coordinates"][:2]
        return GeocodeResult(
            address_line=props.get("name") or props.get("street") or "",
            postal_code=props.get("postcode") or "",
            city=props.get("city") or "",
            citycode=props.get("citycode") or "",
            latitude=Decimal(str(latitude)).quantize(Decimal("0.000001")),
            longitude=Decimal(str(longitude)).quantize(Decimal("0.000001")),
            score=float(props.get("score") or 0),
            kind=props.get("type") or "",
            label=props.get("label") or "",
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def geocode(address: str) -> GeocodeResult | None:
    """Return the best match for an address, or None if nothing reliable is found.

    Args:
        address: Address on one line (``12 rue de la Paix, 75002 Paris``).

    Returns:
        The best result when it is certifiable (see ``GeocodeResult.is_certifiable``).

    Raises:
        GeocodingUnavailable: If the service cannot be reached.
    """
    if not address.strip():
        return None
    results = _search({"q": address, "limit": 1})
    if results and results[0].is_certifiable:
        return results[0]
    return None


def suggest(text: str, limit: int = 5) -> list[GeocodeResult]:
    """Return address suggestions for what the user is typing.

    The answers are cached for a few minutes. A service failure gives an empty list:
    the user can still type the address by hand.

    Args:
        text: Text typed so far.
        limit: Maximum number of suggestions.

    Returns:
        The suggestions, best first (housenumber and street results only).
    """
    text = " ".join(text.split())
    if len(text) < MIN_SUGGESTION_LENGTH:
        return []
    digest = hashlib.sha1(text.lower().encode()).hexdigest()
    key = f"geo-suggest-{limit}-{digest}"
    results = cache.get(key)
    if results is None:
        try:
            results = _search({"q": text, "limit": limit, "autocomplete": 1})
        except GeocodingUnavailable:
            return []
        results = [r for r in results if r.kind in CERTIFIABLE_TYPES]
        cache.set(key, results, SUGGESTIONS_CACHE_SECONDS)
    return results


def certify_address(instance: AddressMixin, *, force: bool = False) -> bool:
    """Compute and store the coordinates of the address of a model.

    Nothing is called when the address has not changed since the last geocoding
    (unless ``force``). A failure never raises: the instance is left uncertified and
    is geocoded again the next time (service down) or only when the address changes
    or ``force`` is given (address not found).

    Args:
        instance: Saved instance of a model with ``AddressMixin``.
        force: Geocode again even if the address did not change.

    Returns:
        True if the address is certified afterwards.
    """
    address = instance.full_address
    if not address and not instance.geocoded_address:
        return False  # never had an address: nothing to geocode nor to store
    if not force and instance.geocoded_at and instance.geocoded_address == address:
        return instance.address_certified

    if address:
        try:
            result = geocode(address)
        except GeocodingUnavailable:
            # Keep what is stored on a forced retry, retry later otherwise
            return instance.address_certified and instance.geocoded_address == address
    else:
        result = None

    instance.geocoded_at = timezone.now()
    instance.geocoded_address = address
    instance.address_certified = result is not None
    instance.latitude = result.latitude if result else None
    instance.longitude = result.longitude if result else None
    if result:
        instance.citycode = result.citycode
    instance.save(update_fields=list(AddressMixin.GEOCODING_FIELDS))
    return instance.address_certified
