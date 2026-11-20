"""Views of the crm app: companies, contacts, archiving, deletion and INSEE search."""

from typing import Any

from core.decorators import htmx_login_required, logged_user
from core.htmx import close_modal, htmx_redirect, htmx_refresh, retarget_modal
from core.http import filter_params
from core.modals import confirm_modal, delete_confirm_modal
from core.pagination import paginate
from core.services import delete_archived_instance
from core.text import agree, plural
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from crm.services.company import (
    apply_sirene_changes,
    get_cessation_alert,
    get_companies_by_name,
    get_company_archive_impact,
    get_company_by_id,
    get_company_delete_blockers,
    get_filtered_companies,
    get_sirene_changes,
    get_sirene_data,
    get_sirene_data_cached,
    update_company,
)
from crm.services.company import (
    create_company as create_company_service,
)
from crm.services.contact import (
    create_contact as create_contact_service,
)
from crm.services.contact import (
    get_contact_archive_impact,
    get_contact_by_id,
    get_contact_delete_blockers,
    get_filtered_contacts,
    update_contact,
)
from crm.services.legal_forms import legal_form_label

from .forms import CompanyForm, ContactForm

# ==========================================
# ==== COMPANY SECTION =====================
# ==========================================


def _companies(request: HttpRequest) -> Any:
    """Return the companies filtered by the ``q``, ``status`` and ``sort`` GET parameters."""
    return get_filtered_companies(
        logged_user(request), **filter_params(request, "q", "status", "sort")
    )


def _contacts(request: HttpRequest) -> Any:
    """Return the contacts filtered by the ``q``, ``company`` and ``status`` GET parameters."""
    return get_filtered_contacts(**filter_params(request, "q", "company", "status"))


def _render_company_grid(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render one page of the filtered companies grid.

    Args:
        request: Current request, with the filters of the list.
        page: Page number.

    Returns:
        The grid partial.
    """
    page_obj = paginate(_companies(request), page)
    return render(
        request,
        "crm/partials/company/company_grid.html",
        {"companies": page_obj, "page_obj": page_obj},
    )


@htmx_login_required
@require_GET
def company_list(request: HttpRequest) -> HttpResponse:
    """Render the companies list page, first page of the filtered list.

    Args:
        request: Current request, with the ``q``, ``status`` and ``sort`` filters.

    Returns:
        The full page.
    """
    companies = _companies(request)

    page_obj = paginate(companies)

    return render(
        request,
        "crm/company.html",
        {
            "companies": page_obj,
            "page_obj": page_obj,
        },
    )


@htmx_login_required
@require_GET
def company_list_paginated(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render only the companies grid of the given page (HTMX).

    Args:
        request: Current request, with the ``q``, ``status`` and ``sort`` filters.
        page: Page number (``core.pagination.PAGE_SIZE`` companies per page).

    Returns:
        The grid partial.
    """
    return _render_company_grid(request, page)


@htmx_login_required
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
    company = get_company_by_id(pk)

    context = {
        "company": company,
    }
    return render(request, "crm/company_detail.html", context)


@htmx_login_required
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
            create_company_service(form, logged_user(request))

            return close_modal(_render_company_grid(request))
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


@htmx_login_required
@require_http_methods(["GET", "POST"])
def company_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the data of a company from its detail page (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the company.

    Returns:
        A 409 if the company is archived. On GET, the pre-filled form
        (``company_update.html``). On a valid POST, the read fragment
        (``company_read.html``). On an invalid POST, the form with its errors
        (``company_update.html``).

    Raises:
        Http404: If the company does not exist.
    """
    company = get_company_by_id(pk)
    if not company.is_active:
        return HttpResponse("Ce client est archivé.", status=409)

    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            company = update_company(form, logged_user(request))
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


@htmx_login_required
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
    company = get_company_by_id(pk)
    return render(
        request,
        "crm/partials/company/company_read.html",
        {"company": company},
    )


def _company_archive_modal(request: HttpRequest, company: Any) -> HttpResponse:
    """Render the archiving modal of a company, listing what follows and what stays.

    Args:
        request: Current request.
        company: Company about to be archived.

    Returns:
        The confirmation modal.
    """
    impact = get_company_archive_impact(company)
    sections = []
    if impact["contacts"]:
        n = len(impact["contacts"])
        sections.append(
            {
                "title": f"{plural(n, 'contact')} {agree(n, 'actif')} "
                f"{agree(n, 'sera', 'seront')} également {agree(n, 'archivé')} :",
                "entries": [
                    f"{c.first_name} {c.last_name}" for c in impact["contacts"]
                ],
                "note": "Au désarchivage du client, ces contacts resteront archivés.",
            }
        )
    if impact["kept_contacts"]:
        n = len(impact["kept_contacts"])
        sections.append(
            {
                "warning": True,
                "title": f"{plural(n, 'contact')} "
                f"{agree(n, 'reste actif', 'restent actifs')} car "
                f"{agree(n, 'référencé')} par un dossier actif :",
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
                "title": f"{plural(n, 'dossier')} d'inspection {agree(n, 'actif')} "
                f"{agree(n, 'est lié', 'sont liés')} à ce client :",
                "entries": [f.reference for f in impact["folders"]],
                "note": "Ces dossiers restent actifs et ne sont pas archivés avec le client.",
            }
        )
    return confirm_modal(
        request,
        title="Archiver ce client ?",
        label=company.name,
        post_url=reverse("crm:company_archive", args=[company.pk]),
        sections=sections,
    )


@htmx_login_required
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
        return _company_archive_modal(request, company)

    company.archive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        return htmx_refresh()

    return redirect("crm:company_detail", pk=company.pk)


@htmx_login_required
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
    company.unarchive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        return htmx_refresh()

    return redirect("crm:company_detail", pk=company.pk)


@htmx_login_required
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


@htmx_login_required
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
                logged_user(request),
                data,
                request.POST.getlist("fields"),
            )
        except ValidationError as e:
            context["error"] = " ".join(e.messages)
            context["changes"] = get_sirene_changes(company, data)
            context["alert"] = get_cessation_alert(data)
            return render(request, template, context, status=422)
        return htmx_refresh()

    context["changes"] = get_sirene_changes(company, data)
    context["alert"] = get_cessation_alert(data)
    return render(request, template, context)


# ==========================================
# ==== CONTACT SECTION =====================
# ==========================================


def _render_contact_grid(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render one page of the filtered contacts grid.

    Args:
        request: Current request, with the filters of the list.
        page: Page number.

    Returns:
        The grid partial.
    """
    page_obj = paginate(_contacts(request), page)
    return render(
        request,
        "crm/partials/contact/contact_grid.html",
        {"contacts": page_obj, "page_obj": page_obj},
    )


@htmx_login_required
@require_GET
def contact_list(request: HttpRequest) -> HttpResponse:
    """Render the contacts list page, first page of the filtered list.

    Args:
        request: Current request, with the ``q``, ``company`` and ``status`` filters.

    Returns:
        The full page.
    """
    companies = get_companies_by_name()
    contacts = _contacts(request)

    page_obj = paginate(contacts)

    return render(
        request,
        "crm/contact.html",
        {
            "contacts": page_obj,
            "page_obj": page_obj,
            "companies": companies,
        },
    )


@htmx_login_required
@require_GET
def contact_list_paginated(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render only the contacts grid of the given page (HTMX).

    Args:
        request: Current request, with the ``q``, ``company`` and ``status`` filters.
        page: Page number (``core.pagination.PAGE_SIZE`` contacts per page).

    Returns:
        The grid partial.
    """
    return _render_contact_grid(request, page)


@htmx_login_required
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
    contact = get_contact_by_id(pk)
    return render(request, "crm/contact_detail.html", {"contact": contact})


@htmx_login_required
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
    # (the POST form field "company" is always present, so only the query string
    # tells that the modal was opened from a company page)
    company_id = request.GET.get("company")

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            create_contact_service(form, logged_user(request))

            # If created from a company detail page, refresh the page to show the new contact
            if company_id:
                return htmx_refresh(status=204)
            # Default behavior for global contact list view
            return close_modal(_render_contact_grid(request))
        else:
            return retarget_modal(
                render(
                    request,
                    "crm/partials/contact/contact_form_modal.html",
                    {"form": form, "from_company": company_id},
                    status=422,
                )
            )
    # Pre-fill company initial data for GET request
    initial_data = {}
    if company_id:
        initial_data["company"] = company_id

    form = ContactForm(initial=initial_data)
    return render(
        request,
        "crm/partials/contact/contact_form_modal.html",
        {"form": form, "from_company": company_id},
    )


@htmx_login_required
@require_http_methods(["GET", "POST"])
def contact_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the data of a contact from its detail page (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the contact.

    Returns:
        A 409 if the contact is archived. On GET, the pre-filled form
        (``contact_update.html``). On a valid POST, the read fragment
        (``contact_read.html``). On an invalid POST, the form with its errors
        (``contact_update.html``).

    Raises:
        Http404: If the contact does not exist.
    """
    contact = get_contact_by_id(pk)
    if not contact.is_active:
        return HttpResponse("Ce contact est archivé.", status=409)

    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            contact = update_contact(form, logged_user(request))
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


@htmx_login_required
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
    contact = get_contact_by_id(pk)
    return render(
        request,
        "crm/partials/contact/contact_read.html",
        {"contact": contact},
    )


@htmx_login_required
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
        blocking = None
        if folders:
            n = len(folders)
            blocking = {
                "title": f"Archivage impossible : {plural(n, 'dossier')} "
                f"{agree(n, 'actif')} {agree(n, 'référence', 'référencent')} ce contact.",
                "entries": [f.reference for f in folders],
                "note": "Changez d'abord le contact référent sur ces dossiers, puis archivez le contact.",
            }
        return confirm_modal(
            request,
            title="Archiver ce contact ?",
            label=f"{contact.first_name} {contact.last_name}",
            post_url=reverse("crm:contact_archive", args=[contact.pk]),
            blocking=blocking,
        )

    if folders.exists():
        return HttpResponse(
            "Ce contact est référencé par un ou plusieurs dossiers actifs.", status=409
        )

    contact.archive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        return htmx_refresh()

    return redirect("crm:contact_detail", pk=contact.pk)


@htmx_login_required
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
    contact.unarchive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        return htmx_refresh()

    return redirect("crm:contact_detail", pk=contact.pk)


@htmx_login_required
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
    folders = get_company_delete_blockers(company)

    blocking = None
    if folders:
        n = len(folders)
        blocking = {
            "title": f"Suppression impossible : {plural(n, 'dossier')} d'inspection "
            f"{agree(n, 'est rattaché', 'sont rattachés')} à ce client.",
            "entries": [f.reference for f in folders],
            "note": "Supprimez d'abord ces dossiers (ils doivent être archivés), puis supprimez le client.",
        }

    if request.method == "GET":
        contacts = company.contacts.all()
        section: dict[str, Any] = {
            "warning": True,
            "title": "Cette action est irréversible.",
        }
        if contacts:
            n = len(contacts)
            section = {
                "warning": True,
                "title": f"{plural(n, 'contact')} "
                f"{agree(n, 'sera supprimé', 'seront supprimés')} avec ce client :",
                "entries": [f"{c.first_name} {c.last_name}" for c in contacts],
                "note": "Cette action est irréversible.",
            }
        return delete_confirm_modal(
            request,
            company,
            title="Supprimer définitivement ce client ?",
            label=company.name,
            post_url=reverse("crm:company_delete", args=[company.pk]),
            sections=[section],
            blocking=blocking,
        )

    if company.is_active:
        return HttpResponse("Le client doit être archivé.", status=409)
    if blocking:
        return HttpResponse(blocking["title"], status=409)

    delete_archived_instance(company)

    if request.headers.get("HX-Request"):
        return htmx_redirect(reverse("crm:company_list"))
    return redirect("crm:company_list")


@htmx_login_required
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
    folders = get_contact_delete_blockers(contact)

    blocking = None
    if folders:
        n = len(folders)
        blocking = {
            "title": f"Suppression impossible : {plural(n, 'dossier')} "
            f"{agree(n, 'référence', 'référencent')} ce contact.",
            "entries": [f.reference for f in folders],
            "note": "Changez d'abord le contact référent sur ces dossiers, puis supprimez le contact.",
        }

    if request.method == "GET":
        return delete_confirm_modal(
            request,
            contact,
            title="Supprimer définitivement ce contact ?",
            label=f"{contact.first_name} {contact.last_name}",
            post_url=reverse("crm:contact_delete", args=[contact.pk]),
            sections=[{"warning": True, "title": "Cette action est irréversible."}],
            blocking=blocking,
        )

    if contact.is_active:
        return HttpResponse("Le contact doit être archivé.", status=409)
    if blocking:
        return HttpResponse(blocking["title"], status=409)

    delete_archived_instance(contact)

    if request.headers.get("HX-Request"):
        return htmx_redirect(reverse("crm:contact_list"))
    return redirect("crm:contact_list")
