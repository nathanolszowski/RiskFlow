from django.db.models import Q
from crm.models import Contact

def get_filtered_contacts(request):
    """Extrait les paramètres de recherche de la requête et renvoie le QuerySet filtré."""
    query = request.GET.get("q", "").strip()
    company_id = request.GET.get("company", "").strip()

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

    return contacts.order_by("-id")