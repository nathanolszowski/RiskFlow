"""Views of the crm app: companies, contacts, archiving, deletion and INSEE search."""

from typing import Any, Optional, cast

from core.services import delete_archived_instance
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from crm.services.company import (
    apply_sirene_changes,
    get_cessation_alert,
    get_company_archive_impact,
    get_company_by_id,
    get_filtered_companies,
    get_sirene_changes,
    get_sirene_data,
    get_sirene_data_cached,
    sync_sirene_status,
)
from crm.services.contact import (
    get_contact_archive_impact,
    get_contact_by_id,
    get_filtered_contacts,
)
from crm.services.legal_forms import legal_form_label

from .forms import CompanyForm, ContactForm
from .models import Company, Contact

# ==========================================
# ==== COMPANY SECTION =====================
# ==========================================


@login_required
@require_GET
def company_list(request: HttpRequest) -> HttpResponse:
    """Render the companies list page, first page of the filtered list.

    Args:
        request: Current request, with the ``q``, ``status`` and ``sort`` filters.

    Returns:
        The full page.
    """
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
def company_list_paginated(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render only the companies grid of the given page (HTMX).

    Args:
        request: Current request, with the ``q``, ``status`` and ``sort`` filters.
        page: Page number, 15 companies per page.

    Returns:
        The grid partial.
    """
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
def company_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the detail page of a company.

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        The full page.

    Raises:
        Http404: If the company does not exist.
    """
    company = get_object_or_404(
        Company.objects.select_related("created_by", "updated_by"), pk=pk
    )

    context = {
        "company": company,
    }
    return render(request, "crm/company_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_company(request: HttpRequest) -> HttpResponse:
    """Render and process the company creation modal (HTMX).

    Args:
        request: Current request.

    Once the company is saved, the Sirene state, head office and NAF 2025 activity are
    read again from its SIRET and stored on it (never taken from the form).

    Returns:
        On GET, the form modal. On a valid POST, the companies grid with
        ``HX-Trigger: closeModal``. On an invalid POST, the modal with a 422 status.
    """
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save(commit=False)
            company.created_by = request.user
            company.save()
            # Store the Sirene state (closed?) and the head office of the client, shown on its page
            sync_sirene_status(company, cast("Any", request.user))

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
def company_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the data of a company from its detail page (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        On GET, the pre-filled form (``company_update.html``). On a valid POST,
        the read fragment (``company_read.html``). On an invalid POST, the form
        with its errors (``company_update.html``).

    Raises:
        Http404: If the company does not exist.
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
def company_inline_read(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the read-only fragment of a company (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        The read fragment (``company_read.html``).

    Raises:
        Http404: If the company does not exist.
    """
    company = get_object_or_404(Company, pk=pk)
    return render(
        request,
        "crm/partials/company/company_read.html",
        {"company": company},
    )


def _refresh_response() -> HttpResponse:
    """Return an HTMX response asking the browser to reload the current page."""
    response = HttpResponse()
    response["HX-Refresh"] = "true"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def company_archive(request: HttpRequest, pk: int) -> HttpResponse:
    """Archive a company and its active contacts.

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        On GET, the confirmation modal listing the impacted contacts and active
        folders. On POST, ``HX-Refresh`` for an HTMX request, otherwise a redirect
        to the company page.

    Raises:
        Http404: If the company does not exist.
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

    company.archive(user=cast("Any", request.user))

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:company_detail", pk=company.pk)


@login_required
@require_POST
def company_unarchive(request: HttpRequest, pk: int) -> HttpResponse:
    """Unarchive a company. Its contacts stay archived.

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        ``HX-Refresh`` for an HTMX request, otherwise a redirect to the company page.

    Raises:
        Http404: If the company does not exist.
    """
    company = get_company_by_id(pk)
    company.unarchive(user=cast("Any", request.user))

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:company_detail", pk=company.pk)


@login_required
@require_GET
def search_siret_api(request: HttpRequest) -> HttpResponse:
    """Query the INSEE API to auto-complete the company creation form (HTMX).

    Args:
        request: Current request. ``siret_search`` holds the SIRET, spaces and
            dashes are ignored.

    Returns:
        The result partial (data injected in the form, legal form, NAF 2025 activity,
        head office and a cessation alert if Sirene reports the establishment closed),
        or an empty response if the SIRET is not 14 digits. The Sirene answer is reused
        for a few minutes (``get_sirene_data_cached``).
    """
    siret_query = (
        request.GET.get("siret_search", "").strip().replace(" ", "").replace("-", "")
    )

    if not siret_query or len(siret_query) != 14 or not siret_query.isdigit():
        return HttpResponse("")

    company_data = get_sirene_data_cached(siret_query)

    if company_data:
        context = {
            "found": True,
            "alert": get_cessation_alert(company_data),
            "legal_structure_label": legal_form_label(
                company_data.get("legal_structure", "")
            ),
            **company_data,
        }
    else:
        context = {"found": False, "query": siret_query}

    return render(request, "crm/partials/company/siret_search_result.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def company_sirene_refresh(request: HttpRequest, pk: int) -> HttpResponse:
    """Offer to update a company with the current Sirene data, field by field (HTMX).

    Only the fields coming from the API can change, and only the ones the user
    ticks. The data is fetched again on POST: the values never come from the form.
    If Sirene reports the company as closed or ceased, the modal shows an alert
    (informative: nothing is modified because of it).

    Args:
        request: Current request. On POST, ``fields`` lists the accepted fields.
        pk: Primary key of the company.

    Returns:
        On GET, the modal with the differences (or a message when there is nothing
        to show). On POST, ``HX-Refresh``, a 409 if the company is archived, or the
        modal again with a message (422) if the API gave nothing or a value is invalid.

    Raises:
        Http404: If the company does not exist.
    """
    company = get_company_by_id(pk)
    template = "crm/partials/company/company_sirene_modal.html"
    context: dict[str, Any] = {"company": company}

    if not company.is_active:
        return HttpResponse("Ce client est archivé.", status=409)

    data = get_sirene_data(company)
    if data is None:
        context["error"] = (
            "Aucune donnée récupérée : SIRET introuvable ou service Sirene indisponible."
        )
        return render(
            request, template, context, status=422 if request.method == "POST" else 200
        )

    if request.method == "POST":
        try:
            apply_sirene_changes(
                company,
                cast("Any", request.user),
                data,
                request.POST.getlist("fields"),
            )
        except ValidationError as e:
            context["error"] = " ".join(e.messages)
            context["changes"] = get_sirene_changes(company, data)
            context["alert"] = get_cessation_alert(data)
            return render(request, template, context, status=422)
        return _refresh_response()

    context["changes"] = get_sirene_changes(company, data)
    context["alert"] = get_cessation_alert(data)
    return render(request, template, context)


# ==========================================
# ==== CONTACT SECTION =====================
# ==========================================


@login_required
@require_GET
def contact_list(request: HttpRequest) -> HttpResponse:
    """Render the contacts list page, first page of the filtered list.

    Args:
        request: Current request, with the ``q``, ``company`` and ``status`` filters.

    Returns:
        The full page.
    """
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
def contact_list_paginated(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render only the contacts grid of the given page (HTMX).

    Args:
        request: Current request, with the ``q``, ``company`` and ``status`` filters.
        page: Page number, 15 contacts per page.

    Returns:
        The grid partial.
    """
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
def contact_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the detail page of a contact.

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        The full page.

    Raises:
        Http404: If the contact does not exist.
    """
    contact = get_object_or_404(
        Contact.objects.select_related("company", "created_by", "updated_by"), pk=pk
    )
    return render(request, "crm/contact_detail.html", {"contact": contact})


@login_required
@require_http_methods(["GET", "POST"])
def create_contact(request: HttpRequest) -> HttpResponse:
    """Render and process the contact creation modal (HTMX).

    The ``company`` parameter (GET or POST) pre-fills the company and means the
    modal was opened from a company page.

    Args:
        request: Current request.

    Returns:
        On GET, the form modal. On a valid POST, a 204 with ``HX-Refresh`` when
        created from a company page, otherwise the contacts grid with
        ``HX-Trigger: closeModal``. On an invalid POST, the modal with a 422 status.
    """
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
def contact_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the data of a contact from its detail page (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        On GET, the pre-filled form (``contact_update.html``). On a valid POST,
        the read fragment (``contact_read.html``). On an invalid POST, the form
        with its errors (``contact_update.html``).

    Raises:
        Http404: If the contact does not exist.
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
def contact_inline_read(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the read-only fragment of a contact (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        The read fragment (``contact_read.html``).

    Raises:
        Http404: If the contact does not exist.
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
def contact_archive(request: HttpRequest, pk: int) -> HttpResponse:
    """Archive a contact, unless an active folder still references it as referent.

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        On GET, the confirmation modal, with a blocking message when active folders
        reference the contact. On POST, a 409 if active folders reference it,
        otherwise ``HX-Refresh`` for an HTMX request or a redirect to the contact.

    Raises:
        Http404: If the contact does not exist.
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

    contact.archive(user=cast("Any", request.user))

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:contact_detail", pk=contact.pk)


@login_required
@require_POST
def contact_unarchive(request: HttpRequest, pk: int) -> HttpResponse:
    """Unarchive a contact.

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        ``HX-Refresh`` for an HTMX request, otherwise a redirect to the contact.

    Raises:
        Http404: If the contact does not exist.
    """
    contact = get_contact_by_id(pk)
    contact.unarchive(user=cast("Any", request.user))

    if request.headers.get("HX-Request"):
        return _refresh_response()

    return redirect("crm:contact_detail", pk=contact.pk)


def _plural(n: int, singular: str, plural: Optional[str] = None) -> str:
    """Return ``'<n> <word>'``, with the word pluralized for n > 1.

    Args:
        n: Quantity.
        singular: Singular form of the word.
        plural: Plural form, ``singular`` followed by ``s`` by default.

    Returns:
        The quantity and the word.
    """
    return f"{n} {singular if n < 2 else plural or singular + 's'}"


def _redirect_response(url: str) -> HttpResponse:
    """Return an HTMX response asking the browser to navigate to the given URL.

    Args:
        url: Destination, sent in the ``HX-Redirect`` header.
    """
    response = HttpResponse()
    response["HX-Redirect"] = url
    return response


@login_required
@require_http_methods(["GET", "POST"])
def company_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Permanently delete an archived company and its contacts.

    Refused while the company is active or still has inspection folders.

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        On GET, the confirmation modal, with a blocking message when the deletion
        is refused. On POST, a 409 when refused, otherwise ``HX-Redirect`` to the
        list for an HTMX request or a redirect to it.

    Raises:
        Http404: If the company does not exist.
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
def contact_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Permanently delete an archived contact.

    Refused while the contact is active or still referenced by an inspection folder.

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        On GET, the confirmation modal, with a blocking message when the deletion
        is refused. On POST, a 409 when refused, otherwise ``HX-Redirect`` to the
        list for an HTMX request or a redirect to it.

    Raises:
        Http404: If the contact does not exist.
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
