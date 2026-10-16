from typing import Any

from core.services import delete_archived_instance
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from crm.services.company import (
    INSEEApiClient,
    get_company_archive_impact,
    get_company_by_id,
    get_filtered_companies,
)
from crm.services.contact import (
    get_contact_archive_impact,
    get_contact_by_id,
    get_filtered_contacts,
)

from .forms import CompanyForm, ContactForm
from .models import Company, Contact

# ==========================================
# ==== COMPANY SECTION =====================
# ==========================================


@login_required
@require_GET
def company_list(request):
    """Render companies list view."""
    companies = get_filtered_companies(request)

    paginator = Paginator(companies, 15)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "crm/company.html",
        {
            "companies": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def company_list_paginated(request, page=1):
    """Render companies list view with update page."""
    companies = get_filtered_companies(request)

    paginator = Paginator(companies, 15)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "crm/partials/company/company_grid.html",
        {
            "companies": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def company_detail(request, pk):
    """Render main view for company detail data."""
    company = get_object_or_404(
        Company.objects.select_related("created_by", "updated_by"), pk=pk
    )

    context = {
        "company": company,
    }
    return render(request, "crm/company_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_company(request):
    """HTMX modal view to render the creation window for companies."""
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save(commit=False)
            company.created_by = request.user
            company.save()

            companies = get_filtered_companies(request)
            paginator = Paginator(companies, 15)
            page_obj = paginator.get_page(1)

            response = render(
                request,
                "crm/partials/company/company_grid.html",
                {"companies": page_obj, "page_obj": page_obj},
            )
            response["HX-Trigger"] = "closeModal"
            return response
        else:
            return render(
                request,
                "crm/partials/company/company_form_modal.html",
                {"form": form},
                status=422,
            )

    form = CompanyForm()
    return render(
        request, "crm/partials/company/company_form_modal.html", {"form": form}
    )


@login_required
@require_http_methods(["GET", "POST"])
def company_inline_update(request, pk):
    """
    HTMX modal view to edit company data.
    - GET  : Render auto-complete form (company_update.html).
    - POST : Update validation.
             If True -> Render read view with data (company_read.html).
             If False -> Render form with errors (company_update.html).
    """
    company = get_object_or_404(Company, pk=pk)

    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            company = form.save(commit=False)
            company.updated_by = request.user
            company.save()
            return render(
                request,
                "crm/partials/company/company_read.html",
                {"company": company, "refresh_tracking": True},
            )
    else:
        form = CompanyForm(instance=company)

    return render(
        request,
        "crm/partials/company/company_update.html",
        {"company": company, "form": form},
    )


@login_required
@require_GET
def company_inline_read(request, pk):
    """
    HTMX view to read only company view from detail view.
    Only fragment (company_read.html).
    """
    company = get_object_or_404(Company, pk=pk)
    return render(
        request,
        "crm/partials/company/company_read.html",
        {"company": company},
    )


def _refresh_response():
    """HTMX response asking the browser to reload the current page."""
    response = HttpResponse()
    response["HX-Refresh"] = "true"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def company_archive(request, pk):
    """
    Archive a company and its active contacts.
    - GET  : Render the confirmation modal, listing the impacted contacts and active folders.
    - POST : Archive the company.
    """
    company = get_company_by_id(pk)

    if request.method == "GET":
        impact = get_company_archive_impact(company)
        sections = []
        if impact["contacts"]:
            n = len(impact["contacts"])
            sections.append(
                {
                    "title": f"{n} contact{'s' if n > 1 else ''} actif{'s' if n > 1 else ''} {'seront' if n > 1 else 'sera'} également archivé{'s' if n > 1 else ''} :",
                    "entries": [
                        str(c.first_name + " " + c.last_name)
                        for c in impact["contacts"]
                    ],
                    "note": "Au désarchivage du client, ces contacts resteront archivés.",
                }
            )
        if impact["kept_contacts"]:
            n = len(impact["kept_contacts"])
            sections.append(
                {
                    "warning": True,
                    "title": f"{n} contact{'s' if n > 1 else ''} {'restent actifs' if n > 1 else 'reste actif'} car référencé{'s' if n > 1 else ''} par un dossier actif :",
                    "entries": [
                        f"{c.first_name} {c.last_name}" for c in impact["kept_contacts"]
                    ],
                }
            )
        if impact["folders"]:
            n = len(impact["folders"])
            sections.append(
                {
                    "warning": True,
                    "title": f"{n} dossier{'s' if n > 1 else ''} d'inspection actif{'s' if n > 1 else ''} {'sont liés' if n > 1 else 'est lié'} à ce client :",
                    "entries": [f.reference for f in impact["folders"]],
                    "note": "Ces dossiers restent actifs et ne sont pas archivés avec le client.",
                }
            )
        return render(
            request,
            "core/partials/modal/archive_confirm_modal.html",
            {
                "title": "Archiver ce client ?",
                "object_label": company.name,
                "post_url": reverse("crm:company_archive", args=[company.pk]),
                "sections": sections,
            },
        )

    company.archive(user=request.user)

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:company_detail", pk=company.pk)


@login_required
@require_POST
def company_unarchive(request, pk):
    """Unarchive a company. Its contacts stay archived."""
    company = get_company_by_id(pk)
    company.unarchive(user=request.user)

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:company_detail", pk=company.pk)


@login_required
@require_GET
def search_siret_api(request):
    """Request data from INSEE API and auto-complete the company creation form"""
    siret_query = (
        request.GET.get("siret_search", "").strip().replace(" ", "").replace("-", "")
    )

    if not siret_query or len(siret_query) != 14 or not siret_query.isdigit():
        return HttpResponse("")

    company_data = INSEEApiClient.fetch_by_siret(siret_query)

    if company_data:
        context = {"found": True, **company_data}
    else:
        context = {"found": False, "query": siret_query}

    return render(request, "crm/partials/company/siret_search_result.html", context)


# ==========================================
# ==== CONTACT SECTION =====================
# ==========================================


@login_required
@require_GET
def contact_list(request):
    """Render contacts list view"""
    companies = Company.objects.all().order_by("name")
    contacts = get_filtered_contacts(request)

    paginator = Paginator(contacts, 15)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "crm/contact.html",
        {
            "contacts": page_obj,
            "page_obj": page_obj,
            "companies": companies,
        },
    )


@login_required
@require_GET
def contact_list_paginated(request, page=1):
    """Render contacts list view with update page"""
    contacts = get_filtered_contacts(request)

    paginator = Paginator(contacts, 15)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "crm/partials/contact/contact_grid.html",
        {
            "contacts": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def contact_detail(request, pk):
    """Render the detail view for a contact"""
    contact = get_object_or_404(
        Contact.objects.select_related("company", "created_by", "updated_by"), pk=pk
    )
    return render(request, "crm/contact_detail.html", {"contact": contact})


@login_required
@require_http_methods(["GET", "POST"])
def create_contact(request):
    """HTMX view to render and process the creation form for contacts."""
    # Retrieve company_id from query parameters (GET) or form submission (POST)
    company_id = request.GET.get("company") or request.POST.get("company")

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.created_by = request.user
            contact.save()

            # If created from a company detail page, refresh the page to show the new contact
            if company_id:
                response = HttpResponse(status=204)
                response["HX-Refresh"] = "true"
                return response
            # Default behavior for global contact list view
            contacts = get_filtered_contacts(request)
            paginator = Paginator(contacts, 15)
            page_obj = paginator.get_page(1)

            response = render(
                request,
                "crm/partials/contact/contact_grid.html",
                {"contacts": page_obj, "page_obj": page_obj},
            )
            response["HX-Trigger"] = "closeModal"
            return response
        else:
            return render(
                request,
                "crm/partials/contact/contact_form_modal.html",
                {"form": form},
                status=422,
            )
    # Pre-fill company initial data for GET request
    initial_data = {}
    if company_id:
        initial_data["company"] = company_id

    form = ContactForm(initial=initial_data)
    return render(
        request, "crm/partials/contact/contact_form_modal.html", {"form": form}
    )


@login_required
@require_http_methods(["GET", "POST"])
def contact_inline_update(request, pk):
    """
    HTMX view to edit contact data from detail view.
    - GET  : Render auto-complete form (contact_update.html).
    - POST : Update validation.
             If True -> Render read view with data (contact_read.html).
             If False -> Render form with errors (contact_update.html).
    """
    contact = get_object_or_404(
        Contact.objects.select_related("company", "created_by", "updated_by"), pk=pk
    )

    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.updated_by = request.user
            contact.save()
            return render(
                request,
                "crm/partials/contact/contact_read.html",
                {"contact": contact, "refresh_tracking": True},
            )
    else:
        form = ContactForm(instance=contact)

    return render(
        request,
        "crm/partials/contact/contact_update.html",
        {"contact": contact, "form": form},
    )


@login_required
@require_GET
def contact_inline_read(request, pk):
    """
    HTMX view to read only contact view from detail view.
    Only fragment (contact_read.html).
    """
    contact = get_object_or_404(
        Contact.objects.select_related("company", "created_by", "updated_by"), pk=pk
    )
    return render(
        request,
        "crm/partials/contact/contact_read.html",
        {"contact": contact},
    )


@login_required
@require_http_methods(["GET", "POST"])
def contact_archive(request, pk):
    """
    Archive a contact, unless an active folder still references it as referent contact.
    - GET  : Render the confirmation modal (blocking message when active folders reference the contact).
    - POST : Archive the contact, or refuse with a 409 if active folders reference it.
    """
    contact = get_contact_by_id(pk)
    folders = get_contact_archive_impact(contact)

    if request.method == "GET":
        context: dict[str, Any] = {
            "title": "Archiver ce contact ?",
            "object_label": f"{contact.first_name} {contact.last_name}",
            "post_url": reverse("crm:contact_archive", args=[contact.pk]),
        }
        if folders:
            n = len(folders)
            context["blocking"] = {
                "title": f"Archivage impossible : {n} dossier{'s' if n > 1 else ''} actif{'s' if n > 1 else ''} {'référencent' if n > 1 else 'référence'} ce contact.",
                "entries": [f.reference for f in folders],
                "note": "Changez d'abord le contact référent sur ces dossiers, puis archivez le contact.",
            }
        return render(
            request, "core/partials/modal/archive_confirm_modal.html", context
        )

    if folders.exists():
        return HttpResponse(
            "Ce contact est référencé par un ou plusieurs dossiers actifs.", status=409
        )

    contact.archive(user=request.user)

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:contact_detail", pk=contact.pk)


@login_required
@require_POST
def contact_unarchive(request, pk):
    """Unarchive a contact."""
    contact = get_contact_by_id(pk)
    contact.unarchive(user=request.user)

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:contact_detail", pk=contact.pk)


def _plural(n, singular, plural=None):
    """Return '<n> <word>' with the word pluralized for n > 1."""
    return f"{n} {singular if n < 2 else plural or singular + 's'}"


def _redirect_response(url):
    """HTMX response asking the browser to navigate to the given URL."""
    response = HttpResponse()
    response["HX-Redirect"] = url
    return response


@login_required
@require_http_methods(["GET", "POST"])
def company_delete(request, pk):
    """
    Permanently delete an archived company and its contacts.
    Refused while the company is active or still has inspection folders.
    - GET  : Render the confirmation modal (blocking message when deletion is refused).
    - POST : Delete the company.
    """
    company = get_company_by_id(pk)
    folders = company.inspection_folders.all()
    contacts = company.contacts.all()

    blocking = None
    if company.is_active:
        blocking = {
            "title": "Suppression impossible : ce client n'est pas archivé.",
            "note": "Archivez d'abord le client, puis supprimez-le.",
        }
    elif folders.exists():
        blocking = {
            "title": f"Suppression impossible : {_plural(len(folders), 'dossier')} d'inspection {'sont rattachés' if len(folders) > 1 else 'est rattaché'} à ce client.",
            "entries": [f.reference for f in folders],
            "note": "Supprimez d'abord ces dossiers (ils doivent être archivés), puis supprimez le client.",
        }

    if request.method == "GET":
        context = {
            "title": "Supprimer définitivement ce client ?",
            "object_label": company.name,
            "action_verb": "supprimer définitivement",
            "confirm_label": "Supprimer définitivement",
            "danger": True,
            "post_url": reverse("crm:company_delete", args=[company.pk]),
            "blocking": blocking,
            "sections": [],
        }
        if contacts:
            context["sections"].append(
                {
                    "warning": True,
                    "title": f"{_plural(len(contacts), 'contact')} {'seront supprimés' if len(contacts) > 1 else 'sera supprimé'} avec ce client :",
                    "entries": [f"{c.first_name} {c.last_name}" for c in contacts],
                    "note": "Cette action est irréversible.",
                }
            )
        else:
            context["sections"].append(
                {"warning": True, "title": "Cette action est irréversible."}
            )
        return render(
            request, "core/partials/modal/archive_confirm_modal.html", context
        )

    if blocking:
        return HttpResponse(blocking["title"], status=409)

    delete_archived_instance(company)

    if request.headers.get("HX-Request"):
        return _redirect_response(reverse("crm:company_list"))
    return redirect("crm:company_list")


@login_required
@require_http_methods(["GET", "POST"])
def contact_delete(request, pk):
    """
    Permanently delete an archived contact.
    Refused while the contact is active or still referenced by an inspection folder.
    - GET  : Render the confirmation modal (blocking message when deletion is refused).
    - POST : Delete the contact.
    """
    contact = get_contact_by_id(pk)
    folders = contact.inspection_folders.all()

    blocking = None
    if contact.is_active:
        blocking = {
            "title": "Suppression impossible : ce contact n'est pas archivé.",
            "note": "Archivez d'abord le contact, puis supprimez-le.",
        }
    elif folders.exists():
        blocking = {
            "title": f"Suppression impossible : {_plural(len(folders), 'dossier')} {'référencent' if len(folders) > 1 else 'référence'} ce contact.",
            "entries": [f.reference for f in folders],
            "note": "Changez d'abord le contact référent sur ces dossiers, puis supprimez le contact.",
        }

    if request.method == "GET":
        return render(
            request,
            "core/partials/modal/archive_confirm_modal.html",
            {
                "title": "Supprimer définitivement ce contact ?",
                "object_label": f"{contact.first_name} {contact.last_name}",
                "action_verb": "supprimer définitivement",
                "confirm_label": "Supprimer définitivement",
                "danger": True,
                "post_url": reverse("crm:contact_delete", args=[contact.pk]),
                "blocking": blocking,
                "sections": [
                    {"warning": True, "title": "Cette action est irréversible."}
                ],
            },
        )

    if blocking:
        return HttpResponse(blocking["title"], status=409)

    delete_archived_instance(contact)

    if request.headers.get("HX-Request"):
        return _redirect_response(reverse("crm:contact_list"))
    return redirect("crm:contact_list")
