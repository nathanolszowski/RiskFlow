"""Travel time between two points with the Géoplateforme route service (no API key)."""

from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings

REQUEST_TIMEOUT = 10
RESOURCE = "bdtopo-osrm"


class RoutingUnavailable(Exception):
    """The route service could not be reached or answered with an error."""


class NoRouteFound(RoutingUnavailable):
    """The service answered but there is no road between the two points."""


@dataclass(frozen=True)
class TravelResult:
    """Fastest car route between two points.

    Attributes:
        minutes: Driving time in whole minutes (at least 1).
        kilometers: Distance in kilometers, one decimal.
    """

    minutes: int
    kilometers: Decimal


def get_travel_time(
    origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]
) -> TravelResult:
    """Return the driving time and distance between two points.

    The route is computed on the road network of the BD TOPO (France), without live
    traffic.

    Args:
        origin: ``(latitude, longitude)`` of the starting point.
        destination: ``(latitude, longitude)`` of the arrival point.

    Returns:
        The fastest car route.

    Raises:
        NoRouteFound: If the service finds no road between the points.
        RoutingUnavailable: If the service cannot be reached or answers an error.
    """
    if not settings.GEOCODING_ENABLED:
        raise RoutingUnavailable("routing disabled")
    try:
        response = requests.get(
            settings.GEOPF_ROUTING_URL,
            params={
                "resource": RESOURCE,
                "start": f"{origin[1]},{origin[0]}",
                "end": f"{destination[1]},{destination[0]}",
                "profile": "car",
                "optimization": "fastest",
                "getSteps": "false",
                "getBbox": "false",
                "distanceUnit": "kilometer",
                "timeUnit": "minute",
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code in (400, 404):
            raise NoRouteFound(f"HTTP {response.status_code}")
        if response.status_code != 200:
            raise RoutingUnavailable(f"HTTP {response.status_code}")
        data = response.json()
        minutes = float(data["duration"])
        kilometers = Decimal(str(data["distance"]))
    except (requests.RequestException, ValueError, KeyError, ArithmeticError) as exc:
        raise RoutingUnavailable(str(exc)) from exc
    return TravelResult(
        minutes=max(1, round(minutes)),
        kilometers=kilometers.quantize(Decimal("0.1")),
    )
