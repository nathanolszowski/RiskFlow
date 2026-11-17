"""Global search of the top bar: folders, clients and contacts."""

from typing import TYPE_CHECKING, Any

from crm.models import Company, Contact
from django.db.models import Q
from inspections.models import InspectionFolder

if TYPE_CHECKING:
    from accounts.models import CustomUser

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 5


def global_search(user: "CustomUser", query: str) -> dict[str, Any]:
    """Search the folders of the user and the shared clients and contacts.

    Folders are private, so only the ones of the user are searched; clients and
    contacts are shared between users, so all of them are.

    Args:
        user: User searching.
        query: Text typed; nothing is searched under two characters.

    Returns:
        ``folders``, ``companies`` and ``contacts``, at most five of each.
    """
    query = query.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return {"folders": [], "companies": [], "contacts": []}
    return {
        "folders": InspectionFolder.objects.filter(
            Q(reference__icontains=query) | Q(company__name__icontains=query),
            created_by=user,
        )[:MAX_RESULTS],
        "companies": Company.objects.filter(
            Q(name__icontains=query)
            | Q(address_line__icontains=query)
            | Q(city__icontains=query)
            | Q(postal_code__icontains=query)
        )[:MAX_RESULTS],
        "contacts": Contact.objects.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )[:MAX_RESULTS],
    }
