from django.db.models import Q
from django.shortcuts import get_object_or_404

from crm.models import Contact


def get_contact_by_id(pk):
    """Return a contact with its company, or raise a 404."""
    return get_object_or_404(
        Contact.objects.select_related(
            "company", "created_by", "updated_by", "archived_by"
        ),
        pk=pk,
    )


def get_contact_archive_impact(contact):
    """Return the active inspection folders that reference this contact."""
    return contact.inspection_folders.filter(is_active=True)


def get_filtered_contacts(request):
    """Extrait les paramètres de recherche de la requête et renvoie le QuerySet filtré."""
    query = request.GET.get("q", "").strip()
    company_id = request.GET.get("company", "").strip()
    status = request.GET.get("status", "active").strip()

    contacts = Contact.objects.select_related("company").all()

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
