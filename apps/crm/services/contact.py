"""Contact services: getters, filtered list, creation and update."""

from typing import TYPE_CHECKING

from core.services import create_tracked_instance, update_tracked_form
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404

from crm.models import Contact

if TYPE_CHECKING:
    from accounts.models import CustomUser

    from crm.forms import ContactForm


def get_contact_by_id(pk: int) -> Contact:
    """Return a contact with its company and tracking users.

    Contacts are shared between all users, like the companies they belong to.

    Args:
        pk: Primary key of the contact.

    Returns:
        The contact.

    Raises:
        Http404: If the contact does not exist.
    """
    return get_object_or_404(
        Contact.objects.select_related(
            "company", "created_by", "updated_by", "archived_by"
        ),
        pk=pk,
    )


def get_contact_archive_impact(contact: Contact) -> QuerySet:
    """Return the active inspection folders that reference this contact.

    Args:
        contact: Contact about to be archived.

    Returns:
        The active folders, which block the archiving when there are some.
    """
    return contact.inspection_folders.filter(is_active=True)


def get_filtered_contacts(
    *, q: str = "", company: str = "", status: str = "active"
) -> QuerySet:
    """Return the contacts (shared between users) filtered, newest first.

    Args:
        q: Search on name, email and company name.
        company: Company id, ignored if not a number.
        status: ``active`` (default), ``archived``, or any other value for all.

    Returns:
        The filtered contacts.
    """
    q = q.strip()
    company = str(company).strip()
    status = status.strip()

    contacts = Contact.objects.select_related("company").all()

    if q:
        contacts = contacts.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(company__name__icontains=q)
        )

    if company.isdigit():
        contacts = contacts.filter(company_id=company)

    if status == "active":
        contacts = contacts.filter(is_active=True)
    elif status == "archived":
        contacts = contacts.filter(is_active=False)

    return contacts.order_by("-id")


def get_contact_delete_blockers(contact: Contact) -> QuerySet:
    """Return the folders that prevent the permanent deletion of a contact.

    Every folder referencing it counts, archived ones included.

    Args:
        contact: Contact about to be deleted.

    Returns:
        The folders referencing the contact.
    """
    return contact.inspection_folders.all()


def create_contact(form: "ContactForm", user: "CustomUser") -> Contact:
    """Create a contact from a valid form.

    Args:
        form: Valid creation form.
        user: User creating the contact.

    Returns:
        The contact.
    """
    return create_tracked_instance(form, user)


def update_contact(form: "ContactForm", user: "CustomUser") -> Contact:
    """Save a valid edit form of a contact.

    Args:
        form: Valid edit form.
        user: User editing the contact.

    Returns:
        The contact.
    """
    return update_tracked_form(form, user)
