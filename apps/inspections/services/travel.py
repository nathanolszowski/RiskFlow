"""Travel time from the inspector to the site of a folder.

The estimate is stored on the folder and only computed when the user asks for it
(``refresh_travel_estimate``): reading a folder never calls the route service.
"""

from typing import TYPE_CHECKING

from core.services.geo import (
    GeocodingUnavailable,
    NoRouteFound,
    RoutingUnavailable,
    geocode,
    get_travel_time,
)
from django.utils import timezone

from inspections.models import InspectionFolder

if TYPE_CHECKING:
    from accounts.models import CustomUser

TRAVEL_FIELDS = [
    "travel_origin_kind",
    "travel_origin_label",
    "travel_origin_latitude",
    "travel_origin_longitude",
    "travel_destination_label",
    "travel_minutes",
    "travel_km",
    "travel_computed_at",
]


class TravelError(Exception):
    """The travel time cannot be computed; the message is shown to the user."""


def has_travel_estimate(folder: InspectionFolder) -> bool:
    """Return whether a travel time was computed for the folder."""
    return folder.travel_computed_at is not None


def is_travel_estimate_stale(folder: InspectionFolder, user: "CustomUser") -> bool:
    """Tell whether the stored estimate no longer matches the addresses.

    It is stale when the site address changed since the computation or, for a trip
    from home, when the home address of the user changed. Nothing is recomputed.

    Args:
        folder: Folder with a stored estimate.
        user: User looking at the folder.

    Returns:
        True if the estimate should be computed again.
    """
    if not has_travel_estimate(folder):
        return False
    if folder.travel_destination_label != folder.full_address:
        return True
    return (
        folder.travel_origin_kind == InspectionFolder.TravelOrigin.HOME
        and folder.travel_origin_label != user.full_address
    )


def refresh_travel_estimate(
    folder: InspectionFolder,
    user: "CustomUser",
    *,
    origin_address: str = "",
    use_home: bool = False,
) -> None:
    """Compute the travel time to the site and store it on the folder.

    The starting point is, in this order: ``origin_address`` (a new custom point, which
    is geocoded), the home of the user when ``use_home`` is set or no custom point is
    stored, otherwise the custom point already stored on the folder. When anything
    fails the previous estimate is left untouched.

    Args:
        folder: Folder to compute the travel time for.
        user: User travelling, whose home is the default starting point.
        origin_address: Address typed as another starting point.
        use_home: Go back to the home of the user.

    Raises:
        TravelError: If the site or the starting point has no certified position or
            the services fail (the message is meant for the user).
    """
    if not folder.has_coordinates or not folder.address_certified:
        raise TravelError(
            "L'adresse du site n'est pas certifiée : corrigez-la pour calculer le trajet."
        )

    origin_address = origin_address.strip()
    if origin_address:
        try:
            result = geocode(origin_address)
        except GeocodingUnavailable:
            raise TravelError("Service d'adresses indisponible, réessayez plus tard.")
        if result is None:
            raise TravelError("Point de départ introuvable : précisez l'adresse.")
        kind = InspectionFolder.TravelOrigin.CUSTOM
        label = f"{result.address_line}, {result.postal_code} {result.city}"
        origin = (result.latitude, result.longitude)
    elif (
        not use_home
        and folder.travel_origin_kind == InspectionFolder.TravelOrigin.CUSTOM
        and folder.travel_origin_latitude is not None
        and folder.travel_origin_longitude is not None
    ):
        kind = InspectionFolder.TravelOrigin.CUSTOM
        label = folder.travel_origin_label
        origin = (folder.travel_origin_latitude, folder.travel_origin_longitude)
    else:
        if not user.address_certified or not user.has_coordinates:
            raise TravelError(
                "Votre adresse n'est pas certifiée : complétez votre profil "
                "ou choisissez un autre point de départ."
            )
        kind = InspectionFolder.TravelOrigin.HOME
        label = user.full_address
        origin = (user.latitude, user.longitude)

    try:
        travel = get_travel_time(origin, (folder.latitude, folder.longitude))
    except NoRouteFound:
        raise TravelError("Aucun itinéraire routier entre ces deux adresses.")
    except RoutingUnavailable:
        raise TravelError("Calcul d'itinéraire indisponible, réessayez plus tard.")

    folder.travel_origin_kind = kind
    folder.travel_origin_label = label
    folder.travel_origin_latitude, folder.travel_origin_longitude = origin
    folder.travel_destination_label = folder.full_address
    folder.travel_minutes = travel.minutes
    folder.travel_km = travel.kilometers
    folder.travel_computed_at = timezone.now()
    folder.save(update_fields=TRAVEL_FIELDS)
