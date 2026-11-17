"""Geocoding and routing of postal addresses with the Géoplateforme (IGN)."""

from .geocoding import (
    GeocodeResult,
    GeocodingUnavailable,
    certify_address,
    geocode,
    suggest,
)
from .routing import (
    NoRouteFound,
    RoutingUnavailable,
    TravelResult,
    get_travel_time,
)

__all__ = [
    "NoRouteFound",
    "RoutingUnavailable",
    "TravelResult",
    "get_travel_time",
    "GeocodeResult",
    "GeocodingUnavailable",
    "certify_address",
    "geocode",
    "suggest",
]
