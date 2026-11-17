"""Views of the inspections app: folders, visits, recommendations and folder tabs."""

from typing import Any

from core.decorators import htmx_login_required, logged_user
from core.htmx import close_modal, htmx_redirect, htmx_refresh, retarget_modal
from core.http import filter_params
from core.modals import confirm_modal, delete_confirm_modal
from core.pagination import paginate
from core.services import delete_archived_instance, update_tracked_form
from core.services.directory import (
    get_companies_with_folders,
    get_company_by_id,
    get_company_or_none,
)
from core.text import agree, plural
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from inspections.services.inspectionfolder import (
    create_folder as create_folder_service,
)
from inspections.services.inspectionfolder import (
    get_company_folders,
    get_filtered_folders,
    get_inspection_folder_by_id,
    update_folder,
)
from inspections.services.recommandation import get_recommandation_by_id
from inspections.services.travel import (
    TravelError,
    is_travel_estimate_stale,
    refresh_travel_estimate,
)
from inspections.services.visit import (
    VisitLockedError,
    create_visit,
    get_next_visit,
    get_visit_by_id,
    get_visits_for_folder,
    set_visit_done,
)

from .forms import (
    InspectionFolderForm,
    InspectionFolderUpdateForm,
    RecommandationUpdateForm,
    VisitCreateForm,
    VisitInstanceUpdateForm,
)
from .models import InspectionFolder

# ==========================================
# ==== INSPECTION FOLDER SECTION ===========
# ==========================================


def _folders(request: HttpRequest) -> Any:
    """Return the folders of the user filtered by the request (GET, then POST).

    Args:
        request: Current request, with the ``q``, ``phase``, ``status``, ``company``
            and ``sort`` filters.

    Returns:
        The filtered folders.
    """
    return get_filtered_folders(
        logged_user(request),
        **filter_params(
            request, "q", "phase", "status", "company", "sort", include_post=True
        ),
    )


def _render_folder_grid(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render one page of the filtered folders grid.

    Args:
        request: Current request, with the filters of the list.
        page: Page number.

    Returns:
        The grid partial.
    """
    page_obj = paginate(_folders(request), page)
    return render(
        request,
        "inspections/partials/folder/folder_grid.html",
        {"folders": page_obj, "page_obj": page_obj},
    )


@htmx_login_required
@require_GET
def folder_list(request: HttpRequest) -> HttpResponse:
    """Render the folders list page (initial page load).

    Args:
        request: Current request, with the ``q``, ``phase``, ``status``, ``company``
            and ``sort`` filters.

    Returns:
        The full page, first page of the filtered list.
    """
    companies = get_companies_with_folders(logged_user(request))
    folders = _folders(request)

    page_obj = paginate(folders)

    return render(
        request,
        "inspections/folders.html",
        {
            "folders": page_obj,
            "page_obj": page_obj,
            "companies": companies,
            "phase_choices": InspectionFolder.Phase.choices,
        },
    )


@htmx_login_required
@require_GET
def folder_contact_field(request: HttpRequest) -> HttpResponse:
    """Render the contact field of the folder creation form for a company (HTMX).

    Called when the company is chosen in the form: only the contacts of that company
    are offered. Without a valid company, the field has no choice.

    Args:
        request: Current request. ``company`` holds the company id.

    Returns:
        The ``contact`` select (``folder_contact_field.html``).
    """
    form = InspectionFolderForm(company=get_company_or_none(request.GET.get("company")))
    return render(
        request,
        "inspections/partials/folder/folder_contact_field.html",
        {"form": form},
    )


@htmx_login_required
@require_GET
def company_folders_panel(request: HttpRequest, company_id: int) -> HttpResponse:
    """Render the panel of the folders of a company, loaded by its detail page (HTMX).

    The crm app only holds a container pointing here: everything about folders
    (list, archived state, "new folder" button) stays in this app.

    Args:
        request: Current request.
        company_id: Primary key of the company.

    Returns:
        The panel, listing the folders of the company created by the user.

    Raises:
        Http404: If the company does not exist.
    """
    company = get_company_by_id(company_id)
    return render(
        request,
        "inspections/partials/folder/company_folders_panel.html",
        {
            "company": company,
            "folders": get_company_folders(company, logged_user(request)),
        },
    )


@htmx_login_required
@require_GET
def folder_list_paginated(request: HttpRequest, page: int = 1) -> HttpResponse:
    """Render only the folders grid of the given page and filters (HTMX).

    Args:
        request: Current request, with the same filters as ``folder_list``.
        page: Page number (``core.pagination.PAGE_SIZE`` folders per page).

    Returns:
        The grid partial.
    """
    return _render_folder_grid(request, page)


@htmx_login_required
@require_GET
def folder_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the detail page of a folder.

    Args:
        request: Current request. The ``tab`` GET parameter is the tab to open
            (used by the visit form to come back to the visits).
        pk: Primary key of the folder.

    Returns:
        The full page.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))

    context = {
        "folder": folder,
        "travel_stale": is_travel_estimate_stale(folder, logged_user(request)),
        "company_folders": get_company_folders(folder.company, logged_user(request)),
        # Lets the visit form send the inspector back to the visits tab (?tab=visit)
        "initial_tab": request.GET.get("tab"),
    }
    return render(request, "inspections/folder_detail.html", context)


@htmx_login_required
@require_http_methods(["GET", "POST"])
def create_folder(request: HttpRequest) -> HttpResponse:
    """Render and process the folder creation modal (HTMX).

    The ``company`` parameter (GET or POST) pre-selects the company, limits the
    contacts to its own and means the modal was opened from a company page.

    Args:
        request: Current request.

    Returns:
        On GET, the form modal (``folder_form_modal.html``). On a valid POST, a 204
        with ``HX-Refresh`` when created from a company page, otherwise the folders
        grid with ``HX-Trigger: closeModal``. On an invalid POST, the modal with its
        errors (422).
    """
    company_id = request.GET.get("company") or request.POST.get("company")
    selected_company = get_company_or_none(company_id)

    if request.method == "POST":
        form = InspectionFolderForm(request.POST, company=selected_company)

        if form.is_valid():
            create_folder_service(form, logged_user(request))

            # From company
            if selected_company:
                return htmx_refresh(status=204)

            # From folders list
            return close_modal(_render_folder_grid(request))

        else:
            return render(
                request,
                "inspections/partials/folder/folder_form_modal.html",
                {"form": form, "selected_company": selected_company},
                status=422,
            )

    initial_data = {}
    if selected_company:
        initial_data["company"] = selected_company

    form = InspectionFolderForm(initial=initial_data, company=selected_company)

    return render(
        request,
        "inspections/partials/folder/folder_form_modal.html",
        {"form": form, "selected_company": selected_company},
    )


@htmx_login_required
@require_http_methods(["GET", "POST"])
def folder_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the data of a folder from the overview tab (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the folder.

    Returns:
        A 409 if the folder is archived. On GET, the pre-filled form
        (``folder_update.html``). On a valid POST, the read fragment
        (``folder_read.html``). On an invalid POST, the form with its errors
        (``folder_update.html``).

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    if not folder.is_active:
        return HttpResponse("Le dossier est archivé.", status=409)

    if request.method == "POST":
        form = InspectionFolderUpdateForm(request.POST, instance=folder)
        if form.is_valid():
            folder = update_folder(form, logged_user(request))
            return render(
                request,
                "inspections/partials/folder/folder_read.html",
                {"folder": folder, "refresh_tracking": True},
            )
    else:
        form = InspectionFolderUpdateForm(instance=folder)

    return render(
        request,
        "inspections/partials/folder/folder_update.html",
        {"folder": folder, "form": form},
    )


@htmx_login_required
@require_GET
def folder_inline_read(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the read-only fragment of a folder in the overview tab (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the folder.

    Returns:
        The read fragment (``folder_read.html``).

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    return render(
        request,
        "inspections/partials/folder/folder_read.html",
        {"folder": folder},
    )


@htmx_login_required
@require_http_methods(["GET", "POST"])
def folder_archive(request: HttpRequest, folder_id: int) -> HttpResponse:
    """Archive a folder together with its visits and recommendations.

    The company and the referent contact are not archived.

    Args:
        request: Current request.
        folder_id: Primary key of the folder.

    Returns:
        On GET, the confirmation modal listing the elements that will be archived.
        On POST, ``HX-Refresh`` for an HTMX request, otherwise a redirect to the folder.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(folder_id, logged_user(request))

    if request.method == "GET":
        visits = folder.visits.filter(is_active=True).count()
        recs = folder.recommandations.filter(is_active=True).count()
        medias = folder.medias.filter(is_active=True).count()
        return confirm_modal(
            request,
            title="Archiver ce dossier ?",
            label=folder.reference,
            post_url=reverse("inspections:folder_archive", args=[folder.pk]),
            sections=[
                {
                    "warning": True,
                    "title": "Tous les éléments liés à ce dossier seront archivés :",
                    "entries": [
                        plural(visits, "visite"),
                        plural(recs, "recommandation"),
                        plural(medias, "média"),
                    ],
                    "note": "Le client et le contact référent ne sont pas archivés. Au désarchivage du dossier, ces éléments seront réactivés (sauf ceux archivés séparément auparavant).",
                }
            ],
        )

    folder.archive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        return htmx_refresh()

    return redirect("inspections:folder_detail", pk=folder.pk)


@htmx_login_required
@require_POST
def folder_unarchive(request: HttpRequest, folder_id: int) -> HttpResponse:
    """Unarchive a folder, with the visits and recommendations archived together with it.

    Args:
        request: Current request.
        folder_id: Primary key of the folder.

    Returns:
        ``HX-Refresh`` for an HTMX request, otherwise a redirect to the folder.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(folder_id, logged_user(request))
    folder.unarchive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        return htmx_refresh()

    return redirect("inspections:folder_detail", pk=folder.pk)


def _kept_medias_entries(obj: Any) -> list[str]:
    """Return the popup line telling that the medias of a visit/recommendation stay on the folder.

    Args:
        obj: Visit or recommendation about to be deleted.

    Returns:
        One entry for the popup, empty if the object has no media.
    """
    count = obj.medias.count()
    if not count:
        return []
    return [
        f"{plural(count, 'média')} {agree(count, 'rattaché')} "
        f"{agree(count, 'conservé')} dans le dossier"
    ]


@htmx_login_required
@require_http_methods(["GET", "POST"])
def folder_delete(request: HttpRequest, folder_id: int) -> HttpResponse:
    """Permanently delete an archived folder with its visits and recommendations.

    Args:
        request: Current request.
        folder_id: Primary key of the folder.

    Returns:
        On GET, the confirmation modal. On POST, a 409 if the folder is still active,
        otherwise ``HX-Redirect`` to the list for an HTMX request or a redirect to it.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(folder_id, logged_user(request))

    if request.method == "GET":
        visits = folder.visits.count()
        recs = folder.recommandations.count()
        medias = folder.medias.count()
        return delete_confirm_modal(
            request,
            folder,
            title="Supprimer définitivement ce dossier ?",
            label=folder.reference,
            post_url=reverse("inspections:folder_delete", args=[folder.pk]),
            sections=[
                {
                    "warning": True,
                    "title": "Seront supprimés avec ce dossier :",
                    "entries": [
                        plural(visits, "visite"),
                        plural(recs, "recommandation"),
                        f"{plural(medias, 'média')} (fichiers supprimés du stockage)",
                    ],
                    "note": "Le client et le contact référent sont conservés. Cette action est irréversible.",
                }
            ],
        )

    if folder.is_active:
        return HttpResponse(
            "Le dossier doit être archivé avant d'être supprimé.", status=409
        )

    delete_archived_instance(folder)

    if request.headers.get("HX-Request"):
        return htmx_redirect(reverse("inspections:folder_list"))
    return redirect("inspections:folder_list")


# ==========================================
# ==== VISIT SECTION =======================
# ==========================================


@htmx_login_required
@require_http_methods(["GET", "POST"])
def visit_create(request: HttpRequest, folder_id: int) -> HttpResponse:
    """Prepare a new visit from a template (own or shared) and a date (HTMX).

    Args:
        request: Current request. On GET, ``template`` pre-selects a template.
        folder_id: Primary key of the folder.

    Returns:
        A 409 if the folder is archived. On GET, the modal
        (``visit_create_modal.html``). On a valid POST, the visit tab with
        ``HX-Trigger: closeModal``; the visit holds a snapshot of the template. On an
        invalid POST, the modal with its errors (422).

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(folder_id, logged_user(request))
    if not folder.is_active:
        return HttpResponse("Le dossier est archivé.", status=409)

    if request.method == "POST":
        form = VisitCreateForm(request.POST, user=logged_user(request))
        if form.is_valid():
            try:
                create_visit(
                    folder,
                    form.cleaned_data["template"],
                    form.cleaned_data["due_date"],
                    logged_user(request),
                    due_time=form.cleaned_data["due_time"],
                )
            except ValidationError as e:
                form.add_error("template", e)
            else:
                return close_modal(_render_visit_tab(request, folder))
        response = render(
            request,
            "inspections/partials/visit/visit_create_modal.html",
            {"folder": folder, "form": form},
            status=422,
        )
        # The form targets the tab: the invalid modal must replace the modal instead
        return retarget_modal(response)

    form = VisitCreateForm(
        user=logged_user(request),
        initial={
            "template": request.GET.get("template"),
            "due_date": timezone.localdate(),
        },
    )
    return render(
        request,
        "inspections/partials/visit/visit_create_modal.html",
        {"folder": folder, "form": form},
    )


@htmx_login_required
@require_http_methods(["GET", "POST"])
def visit_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the planning data of a visit (date and notes) in a modal (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        A 409 if the visit or its folder is archived. On GET, the form
        (``visit_update_modal.html``). On a valid POST, the visit tab with
        ``HX-Trigger: closeModal``. On an invalid POST, the form with its errors (422).

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, logged_user(request))
    if not visit.is_active or not visit.folder.is_active:
        return HttpResponse("La visite ou son dossier est archivé.", status=409)

    if request.method == "POST":
        form = VisitInstanceUpdateForm(request.POST, instance=visit)
        if form.is_valid():
            visit = update_tracked_form(form, logged_user(request))
            return close_modal(_render_visit_tab(request, visit.folder))
        response = render(
            request,
            "inspections/partials/visit/visit_update_modal.html",
            {"visit": visit, "form": form},
            status=422,
        )
        # The form targets the tab: the invalid modal must replace the modal instead
        return retarget_modal(response)

    form = VisitInstanceUpdateForm(instance=visit)
    return render(
        request,
        "inspections/partials/visit/visit_update_modal.html",
        {"visit": visit, "form": form},
    )


@htmx_login_required
@require_POST
def visit_toggle_done(request: HttpRequest, pk: int) -> HttpResponse:
    """Tick or untick a visit as done from the visits tab.

    Args:
        request: Current request. The ``done`` checkbox is posted as ``on`` when ticked.
        pk: Primary key of the visit.

    Returns:
        The visit tab, or a 409 if the visit is archived.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, logged_user(request))
    try:
        set_visit_done(visit, logged_user(request), request.POST.get("done") == "on")
    except VisitLockedError:
        return HttpResponse("La visite est archivée.", status=409)
    return _render_visit_tab(request, visit.folder)


@htmx_login_required
@require_POST
def visit_archive(request: HttpRequest, pk: int) -> HttpResponse:
    """Archive a visit.

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        The current tab for an HTMX request, otherwise a redirect to the folder.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, logged_user(request))
    visit.archive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_visit_tab(request, visit.folder)

    return redirect("inspections:folder_detail", pk=visit.folder_id)


@htmx_login_required
@require_POST
def visit_unarchive(request: HttpRequest, pk: int) -> HttpResponse:
    """Unarchive a visit, unless its folder is archived.

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        A 409 if the folder is archived (unarchive the folder instead). Otherwise
        the current tab for an HTMX request, or a redirect to the folder.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, logged_user(request))
    if not visit.folder.is_active:
        return HttpResponse("Le dossier est archivé.", status=409)
    visit.unarchive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_visit_tab(request, visit.folder)

    return redirect("inspections:folder_detail", pk=visit.folder_id)


@htmx_login_required
@require_http_methods(["GET", "POST"])
def visit_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Permanently delete an archived visit.

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        On GET, the confirmation modal. On POST, a 409 if the visit is still active,
        otherwise the visit tab for an HTMX request or a redirect to the folder.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, logged_user(request))

    if request.method == "GET":
        return delete_confirm_modal(
            request,
            visit,
            title="Supprimer définitivement cette visite ?",
            label=visit.display_template_name,
            post_url=reverse("inspections:visit_delete", args=[visit.pk]),
            post_target="#tab-content",
            sections=[
                {
                    "warning": True,
                    "title": "Cette action est irréversible.",
                    "entries": _kept_medias_entries(visit),
                }
            ],
        )

    if visit.is_active:
        return HttpResponse(
            "La visite doit être archivée avant d'être supprimée.", status=409
        )

    folder = visit.folder
    delete_archived_instance(visit)

    if request.headers.get("HX-Request"):
        return _render_visit_tab(request, folder)
    return redirect("inspections:folder_detail", pk=folder.pk)


# ==========================================
# ==== RECOMMANDATION SECTION ==============
# ==========================================


@htmx_login_required
@require_http_methods(["GET", "POST"])
def recommandation_inline_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a recommendation from the recommendations tab (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the recommendation.

    Returns:
        A 409 if the recommendation or its folder is archived. On GET, the pre-filled
        form (``recommandation_update.html``). On a valid POST, the read fragment
        (``recommandation_read.html``). On an invalid POST, the form with its errors
        (``recommandation_update.html``).

    Raises:
        Http404: If the recommendation does not exist or its folder belongs to
            another user.
    """
    rec = get_recommandation_by_id(pk, logged_user(request))
    if not rec.is_active or not rec.folder.is_active:
        return HttpResponse("La recommandation ou son dossier est archivé.", status=409)

    if request.method == "POST":
        form = RecommandationUpdateForm(request.POST, instance=rec)
        if form.is_valid():
            rec = update_tracked_form(form, logged_user(request))
            return render(
                request,
                "inspections/partials/recommandation/recommandation_read.html",
                {"rec": rec},
            )
    else:
        form = RecommandationUpdateForm(instance=rec)

    return render(
        request,
        "inspections/partials/recommandation/recommandation_update.html",
        {"rec": rec, "form": form},
    )


@htmx_login_required
@require_GET
def recommandation_inline_read(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the read-only fragment of a recommendation (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the recommendation.

    Returns:
        The read fragment (``recommandation_read.html``).

    Raises:
        Http404: If the recommendation does not exist or its folder belongs to
            another user.
    """
    rec = get_recommandation_by_id(pk, logged_user(request))
    return render(
        request,
        "inspections/partials/recommandation/recommandation_read.html",
        {"rec": rec},
    )


@htmx_login_required
@require_POST
def recommandation_archive(request: HttpRequest, pk: int) -> HttpResponse:
    """Archive a recommendation.

    Args:
        request: Current request.
        pk: Primary key of the recommendation.

    Returns:
        The current tab for an HTMX request, otherwise a redirect to the folder.

    Raises:
        Http404: If the recommendation does not exist or its folder belongs to
            another user.
    """
    rec = get_recommandation_by_id(pk, logged_user(request))
    rec.archive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_recommandations_tab(request, rec.folder)

    return redirect("inspections:folder_detail", pk=rec.folder_id)


@htmx_login_required
@require_POST
def recommandation_unarchive(request: HttpRequest, pk: int) -> HttpResponse:
    """Unarchive a recommendation, unless its folder is archived.

    Args:
        request: Current request.
        pk: Primary key of the recommendation.

    Returns:
        A 409 if the folder is archived (unarchive the folder instead). Otherwise
        the current tab for an HTMX request, or a redirect to the folder.

    Raises:
        Http404: If the recommendation does not exist or its folder belongs to
            another user.
    """
    rec = get_recommandation_by_id(pk, logged_user(request))
    if not rec.folder.is_active:
        return HttpResponse("Le dossier est archivé.", status=409)
    rec.unarchive(user=logged_user(request))

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_recommandations_tab(request, rec.folder)

    return redirect("inspections:folder_detail", pk=rec.folder_id)


@htmx_login_required
@require_http_methods(["GET", "POST"])
def recommandation_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Permanently delete an archived recommendation.

    Args:
        request: Current request.
        pk: Primary key of the recommendation.

    Returns:
        On GET, the confirmation modal. On POST, a 409 if the recommendation is still
        active, otherwise the recommendations tab for an HTMX request or a redirect to
        the folder.

    Raises:
        Http404: If the recommendation does not exist or its folder belongs to
            another user.
    """
    rec = get_recommandation_by_id(pk, logged_user(request))

    if request.method == "GET":
        return delete_confirm_modal(
            request,
            rec,
            title="Supprimer définitivement cette recommandation ?",
            label=f"REC-{rec.pk}",
            post_url=reverse("inspections:recommandation_delete", args=[rec.pk]),
            post_target="#tab-content",
            sections=[
                {
                    "warning": True,
                    "title": "Cette action est irréversible.",
                    "entries": _kept_medias_entries(rec),
                }
            ],
        )

    if rec.is_active:
        return HttpResponse(
            "La recommandation doit être archivée avant d'être supprimée.", status=409
        )

    folder = rec.folder
    delete_archived_instance(rec)

    if request.headers.get("HX-Request"):
        return _render_recommandations_tab(request, folder)
    return redirect("inspections:folder_detail", pk=folder.pk)


# ==========================================
# ==== FOLDER TABS SECTION =================
# ==========================================


@htmx_login_required
@require_GET
def folder_tab_overview(request: HttpRequest, pk: int) -> HttpResponse:
    """Render only the content of the overview tab.

    Args:
        request: Current request.
        pk: Primary key of the folder.

    Returns:
        The tab fragment.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    return render(
        request,
        "inspections/partials/tabs/tab_overview.html",
        {
            "folder": folder,
            "travel_stale": is_travel_estimate_stale(folder, logged_user(request)),
            "company_folders": get_company_folders(
                folder.company, logged_user(request)
            ),
        },
    )


@htmx_login_required
@require_POST
def folder_travel(request: HttpRequest, pk: int) -> HttpResponse:
    """Compute the travel time to the site of a folder and store it (HTMX).

    The only place where the route service is called: displaying a folder never
    recomputes the estimate.

    Args:
        request: Current request. ``origin_address`` is another starting point to
            geocode, ``use_home`` goes back to the home of the user; without them
            the starting point already stored (or the home) is used again.
        pk: Primary key of the folder.

    Returns:
        The travel card. On an error (uncertified address, service down...) it shows the
        message with a 422 status and keeps the previous estimate.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    if not folder.is_active:
        return HttpResponse(status=409)
    error = ""
    try:
        refresh_travel_estimate(
            folder,
            logged_user(request),
            origin_address=request.POST.get("origin_address", ""),
            use_home=bool(request.POST.get("use_home")),
        )
    except TravelError as exc:
        error = str(exc)
    return render(
        request,
        "inspections/partials/folder/folder_travel.html",
        {
            "folder": folder,
            "travel_stale": is_travel_estimate_stale(folder, logged_user(request)),
            "travel_error": error,
        },
        status=422 if error else 200,
    )


def _render_visit_tab(request: HttpRequest, folder: InspectionFolder) -> HttpResponse:
    """Render the visit tab content: next visit, table of the visits and counters.

    Args:
        request: Current request. ``status=archived`` lists the archived visits instead
            of the active ones.
        folder: Folder of the visits.

    Returns:
        The tab fragment.
    """
    status = "archived" if request.GET.get("status") == "archived" else "active"
    return render(
        request,
        "inspections/partials/tabs/tab_visit.html",
        {
            "folder": folder,
            "status": status,
            "visits": get_visits_for_folder(folder, status),
            "next_visit": get_next_visit(folder),
            "active_count": folder.visits.filter(is_active=True).count(),
            "archived_count": folder.visits.filter(is_active=False).count(),
        },
    )


@htmx_login_required
@require_GET
def folder_tab_visit(request: HttpRequest, pk: int) -> HttpResponse:
    """Render only the content of the visit tab.

    Args:
        request: Current request.
        pk: Primary key of the folder.

    Returns:
        The tab fragment.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    return _render_visit_tab(request, folder)


def _render_recommandations_tab(
    request: HttpRequest, folder: InspectionFolder
) -> HttpResponse:
    """Render the recommendations tab content.

    Args:
        request: Current request.
        folder: Folder of the recommendations.

    Returns:
        The tab fragment.
    """
    return render(
        request,
        "inspections/partials/tabs/tab_recommandations.html",
        {
            "recommandations": folder.recommandations.select_related(
                "created_by", "updated_by"
            ),
            "active_count": folder.recommandations.filter(is_active=True).count(),
        },
    )


@htmx_login_required
@require_GET
def folder_tab_recommandations(request: HttpRequest, pk: int) -> HttpResponse:
    """Render only the content of the recommendations tab.

    Args:
        request: Current request.
        pk: Primary key of the folder.

    Returns:
        The tab fragment.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    return _render_recommandations_tab(request, folder)


@htmx_login_required
@require_GET
def folder_tab_reports(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the placeholder of the reports tab (not implemented yet).

    Args:
        request: Current request.
        pk: Primary key of the folder.

    Returns:
        The "under construction" tab fragment.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, logged_user(request))
    return render(
        request, "inspections/partials/tabs/tab_reports.html", {"folder": folder}
    )
