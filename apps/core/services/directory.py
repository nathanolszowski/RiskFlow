"""Access of the other apps to the companies of crm.

``inspections`` depends on ``crm`` through its foreign keys only (given as strings,
``"crm.Company"``). Whatever else it needs from crm goes through this module, so that
it never imports ``crm`` itself.
"""

from typing import TYPE_CHECKING, Optional

from crm.models import Company
from crm.services.company import get_company_by_id

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models import QuerySet

__all__ = [
    "get_companies_with_folders",
    "get_company_by_id",
    "get_company_or_none",
]


def get_companies_with_folders(user: "CustomUser") -> "QuerySet[Company]":
    """Return the companies that have at least one inspection folder of the user, by name.

    Companies are shared between users, folders are not: only the companies of the
    user's own folders are listed.

    Args:
        user: Owner of the folders.

    Returns:
        The companies, without duplicates.
    """
    return (
        Company.objects.filter(inspection_folders__created_by=user)
        .distinct()
        .order_by("name")
    )


def get_company_or_none(pk: object) -> Optional[Company]:
    """Return the company with the given primary key, or None.

    Companies are shared between all users.

    Args:
        pk: Raw primary key, e.g. a query string value. Empty or invalid gives None.

    Returns:
        The company, or None if there is none.
    """
    if not pk:
        return None
    try:
        return Company.objects.filter(pk=pk).first()
    except (TypeError, ValueError):
        return None
