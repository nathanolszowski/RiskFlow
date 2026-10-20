"""Contact services: getters and filtered list."""

from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from crm.models import Contact

if TYPE_CHECKING:
    from accounts.models import CustomUser


def get_contact_by_id(pk: int, user: "CustomUser") -> Contact:
    """Return a contact with its company and tracking users.

    Restricted to the contacts created by the user.

    Args:
        pk: Primary key of the contact.
        user: Logged-in user, who must have created the contact.

    Returns:
        The contact.

    Raises:
        Http404: If the contact does not exist or belongs to another user.
    """
    return get_object_or_404(
        Contact.objects.select_related(
            "company", "created_by", "updated_by", "archived_by"
        ),
        pk=pk,
        created_by=user,
    )


def get_contact_archive_impact(contact: Contact) -> QuerySet:
    """Return the active inspection folders that reference this contact.

    Args:
        contact: Contact about to be archived.

    Returns:
        The active folders, which block the archiving when there are some.
    """
    return contact.inspection_folders.filter(is_active=True)


def get_filtered_contacts(request: HttpRequest) -> QuerySet:
    """Return the contacts filtered by the GET parameters, newest first.

    Args:
        request: Current request. Reads ``q`` (search on name, email and company
            name), ``company`` (company id), and ``status`` (``active`` by
            default, ``archived``, or any other value for all contacts).

    Returns:
        The filtered contacts.
    """
    query = request.GET.get("q", "").strip()
    company_id = request.GET.get("company", "").strip()
    status = request.GET.get("status", "active").strip()

    contacts = Contact.objects.select_related("company").filter(created_by=request.user)

    if query:
        contacts = contacts.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(company__name__icontains=query)
        )

    if company_id and company_id.isdigit():
        contacts = contacts.filter(company_id=company_id)

    if status == "active":
        contacts = contacts.filter(is_active=True)
    elif status == "archived":
        contacts = contacts.filter(is_active=False)

    return contacts.order_by("-id")
