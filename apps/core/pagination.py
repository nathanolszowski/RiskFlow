"""Pagination shared by the lists of the apps (clients, contacts, folders)."""

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet

PAGE_SIZE = 15


def paginate(queryset: QuerySet, page: int | str = 1) -> Page:
    """Return one page of a list, ``PAGE_SIZE`` items per page.

    Args:
        queryset: Ordered items of the list.
        page: Page number; an invalid one gives the first page, one beyond the end
            the last page (``Paginator.get_page``).

    Returns:
        The page.
    """
    return Paginator(queryset, PAGE_SIZE).get_page(page)
