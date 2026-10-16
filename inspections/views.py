from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.core.paginator import Paginator
from core.services import delete_archived_instance
from django.forms import ModelChoiceField
from django.http import HttpResponse
from .forms import InspectionFolderForm, InspectionFolderUpdateForm, VisitInstanceUpdateForm, RecommandationUpdateForm
from .models import InspectionFolder
from crm.models import Company, Contact
from inspections.services.inspectionfolder import get_filtered_folders, get_inspection_folder_by_id, create_tracked_instance
from inspections.services.visit import get_visit_by_id
from inspections.services.recommandation import get_recommandation_by_id


# ==========================================
# ==== INSPECTION FOLDER SECTION ===========
# ==========================================

@login_required
@require_GET
def folder_list(request):
    """Render inspection folders list view (initial page load)."""
    companies = (
        Company.objects.filter(inspection_folders__isnull=False)
        .distinct()
        .order_by("name")
    )
    folders = get_filtered_folders(request)

    paginator = Paginator(folders, 15)
    page_obj = paginator.get_page(1)

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


@login_required
@require_GET
def folder_list_paginated(request, page=1):
    """Render inspection folders list view with updated page / filters (HTMX)."""
    folders = get_filtered_folders(request)

    paginator = Paginator(folders, 15)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "inspections/partials/folder_grid.html",
        {
            "folders": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def folder_detail(request, pk):
    """Render main view for inspection folder detail data."""
    folder = get_inspection_folder_by_id(pk, request.user)

    context = {
        "folder": folder,
    }
    return render(request, "inspections/folder_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_folder(request):
    """HTMX view to create a new inspection folder
    - GET  : Render the form in a modal (folder_form_modal.html).
    - POST : Validate the form and create the folder.
             If True -> Return 204 to close the modal and refresh the list.
             If False -> Render the form with errors (folder_form_modal.html).
    """
    company_id = request.GET.get("company") or request.POST.get("company")
    selected_company = Company.objects.filter(pk=company_id).first() if company_id else None

    if request.method == "POST":
        form = InspectionFolderForm(request.POST)

        if selected_company:
            contact_field = form.fields['contact']
            if isinstance(contact_field, ModelChoiceField):
                contact_field.queryset = Contact.objects.filter(company=selected_company)

        if form.is_valid():
            create_tracked_instance(form, request.user)

            # From company
            if selected_company:
                response = HttpResponse(status=204)
                response["HX-Refresh"] = "true"
                return response

            # From folders list
            folders = get_filtered_folders(request)
            paginator = Paginator(folders, 15)
            page_obj = paginator.get_page(1)

            response = render(
                request,
                "inspections/partials/folder_grid.html",
                {"folders": page_obj, "page_obj": page_obj},
            )
            response["HX-Trigger"] = "closeModal"
            return response

        else:
            return render(
                request,
                "inspections/partials/folder_form_modal.html",
                {"form": form, "selected_company": selected_company},
                status=422,
            )

    initial_data = {}
    if selected_company:
        initial_data["company"] = selected_company

    form = InspectionFolderForm(initial=initial_data)

    if selected_company:
        contact_field = form.fields['contact']
        if isinstance(contact_field, ModelChoiceField):
            contact_field.queryset = Contact.objects.filter(company=selected_company)

    return render(
        request, 
        "inspections/partials/folder_form_modal.html", 
        {"form": form, "selected_company": selected_company}
    )

@login_required
@require_http_methods(["GET", "POST"])
def folder_inline_update(request, pk):
    """
    HTMX view to edit folder data from the overview tab.
    - GET  : Render auto-complete form (folder_update.html).
    - POST : Update validation.
             If True -> Render read view with data (folder_read.html).
             If False -> Render form with errors (folder_update.html).
    """
    folder = get_inspection_folder_by_id(pk, request.user)

    if request.method == "POST":
        form = InspectionFolderUpdateForm(request.POST, instance=folder)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.updated_by = request.user
            folder.save()
            return render(
                request,
                "inspections/partials/folder_read.html",
                {"folder": folder, "refresh_tracking": True},
            )
    else:
        form = InspectionFolderUpdateForm(instance=folder)

    return render(
        request,
        "inspections/partials/folder_update.html",
        {"folder": folder, "form": form},
    )


@login_required
@require_GET
def folder_inline_read(request, pk):
    """
    HTMX view to read only folder information from the overview tab.
    Only fragment (folder_read.html).
    """
    folder = get_inspection_folder_by_id(pk, request.user)
    return render(
        request,
        "inspections/partials/folder_read.html",
        {"folder": folder},
    )


@login_required
@require_http_methods(["GET", "POST"])
def folder_archive(request, folder_id):
    """
    Archive a folder together with its visits and recommendations (not its company or contact).
    - GET  : Render the confirmation modal listing the elements that will be archived.
    - POST : Archive the folder.
    """
    folder = get_inspection_folder_by_id(folder_id, request.user)

    if request.method == "GET":
        visits = folder.visits.filter(is_active=True).count()
        recs = folder.recommandations.filter(is_active=True).count()
        items = [
            f"{visits} visite{'s' if visits > 1 else ''}",
            f"{recs} recommandation{'s' if recs > 1 else ''}",
        ]
        return render(
            request,
            "core/partials/archive_confirm_modal.html",
            {
                "title": "Archiver ce dossier ?",
                "object_label": folder.reference,
                "post_url": reverse("inspections:folder_archive", args=[folder.pk]),
                "sections": [{
                    "warning": True,
                    "title": "Tous les éléments liés à ce dossier seront archivés :",
                    "entries": items,
                    "note": "Le client et le contact référent ne sont pas archivés. Au désarchivage du dossier, ces éléments seront réactivés (sauf ceux archivés séparément auparavant).",
                }],
            },
        )

    folder.archive(user=request.user)

    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    return redirect("inspections:folder_detail", pk=folder.pk)


@login_required
@require_POST
def folder_unarchive(request, folder_id):
    folder = get_inspection_folder_by_id(folder_id, request.user)
    folder.unarchive(user=request.user)

    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    return redirect("inspections:folder_detail", pk=folder.pk)

def _delete_modal(request, obj, *, title, label, post_url, sections, post_target=None):
    """Render the permanent-deletion modal; it only offers confirmation once the object is archived."""
    blocking = None
    if obj.is_active:
        blocking = {
            "title": "Suppression impossible : cet élément n'est pas archivé.",
            "note": "Archivez-le d'abord, puis supprimez-le.",
        }
    return render(
        request,
        "core/partials/archive_confirm_modal.html",
        {
            "title": title,
            "object_label": label,
            "action_verb": "supprimer définitivement",
            "confirm_label": "Supprimer définitivement",
            "danger": True,
            "post_url": post_url,
            "post_target": post_target,
            "blocking": blocking,
            "sections": sections,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def folder_delete(request, folder_id):
    """
    Permanently delete an archived folder with its visits and recommendations.
    - GET  : Render the confirmation modal.
    - POST : Delete the folder (409 if it is still active).
    """
    folder = get_inspection_folder_by_id(folder_id, request.user)

    if request.method == "GET":
        visits = folder.visits.count()
        recs = folder.recommandations.count()
        return _delete_modal(
            request, folder,
            title="Supprimer définitivement ce dossier ?",
            label=folder.reference,
            post_url=reverse("inspections:folder_delete", args=[folder.pk]),
            sections=[{
                "warning": True,
                "title": "Seront supprimés avec ce dossier :",
                "entries": [
                    f"{visits} visite{'s' if visits > 1 else ''}",
                    f"{recs} recommandation{'s' if recs > 1 else ''}",
                ],
                "note": "Le client et le contact référent sont conservés. Cette action est irréversible.",
            }],
        )

    if folder.is_active:
        return HttpResponse("Le dossier doit être archivé avant d'être supprimé.", status=409)

    delete_archived_instance(folder)

    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Redirect"] = reverse("inspections:folder_list")
        return response
    return redirect("inspections:folder_list")

# ==========================================
# ==== VISIT SECTION =======================
# ==========================================

@login_required
@require_http_methods(["GET", "POST"])
def visit_inline_update(request, pk):
    """
    HTMX view to edit visit planning data from the visit tab.
    - GET  : Render auto-complete form (visit_update.html).
    - POST : Update validation.
             If True -> Render read view with data (visit_read.html).
             If False -> Render form with errors (visit_update.html).
    """
    visit = get_visit_by_id(pk, request.user)

    if request.method == "POST":
        form = VisitInstanceUpdateForm(request.POST, instance=visit)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.updated_by = request.user
            visit.save()
            return render(
                request,
                "inspections/partials/visit_read.html",
                {"visit": visit},
            )
    else:
        form = VisitInstanceUpdateForm(instance=visit)

    return render(
        request,
        "inspections/partials/visit_update.html",
        {"visit": visit, "form": form},
    )


@login_required
@require_GET
def visit_inline_read(request, pk):
    """
    HTMX view to read only visit planning data from the visit tab.
    Only fragment (visit_read.html).
    """
    visit = get_visit_by_id(pk, request.user)
    return render(
        request,
        "inspections/partials/visit_read.html",
        {"visit": visit},
    )



@login_required
@require_POST
def visit_archive(request, pk):
    visit = get_visit_by_id(pk, request.user)
    visit.archive(user=request.user)

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_visit_tab(request, visit.folder)

    return redirect("inspections:folder_detail", pk=visit.folder_id)


@login_required
@require_POST
def visit_unarchive(request, pk):
    visit = get_visit_by_id(pk, request.user)
    visit.unarchive(user=request.user)

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_visit_tab(request, visit.folder)

    return redirect("inspections:folder_detail", pk=visit.folder_id)



@login_required
@require_http_methods(["GET", "POST"])
def visit_delete(request, pk):
    """
    Permanently delete an archived visit.
    - GET  : Render the confirmation modal.
    - POST : Delete the visit and re-render the visit tab (409 if it is still active).
    """
    visit = get_visit_by_id(pk, request.user)

    if request.method == "GET":
        return _delete_modal(
            request, visit,
            title="Supprimer définitivement cette visite ?",
            label=visit.template.name,
            post_url=reverse("inspections:visit_delete", args=[visit.pk]),
            post_target="#tab-content",
            sections=[{"warning": True, "title": "Cette action est irréversible."}],
        )

    if visit.is_active:
        return HttpResponse("La visite doit être archivée avant d'être supprimée.", status=409)

    folder = visit.folder
    delete_archived_instance(visit)

    if request.headers.get("HX-Request"):
        return _render_visit_tab(request, folder)
    return redirect("inspections:folder_detail", pk=folder.pk)


# ==========================================
# ==== RECOMMANDATION SECTION ==============
# ==========================================

@login_required
@require_http_methods(["GET", "POST"])
def recommandation_inline_update(request, pk):
    """
    HTMX view to edit a recommendation from the recommendations tab.
    - GET  : Render auto-complete form (recommandation_update.html).
    - POST : Update validation.
             If True -> Render read view with data (recommandation_read.html).
             If False -> Render form with errors (recommandation_update.html).
    """
    rec = get_recommandation_by_id(pk, request.user)

    if request.method == "POST":
        form = RecommandationUpdateForm(request.POST, instance=rec)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.updated_by = request.user
            rec.save()
            return render(
                request,
                "inspections/partials/recommandation_read.html",
                {"rec": rec},
            )
    else:
        form = RecommandationUpdateForm(instance=rec)

    return render(
        request,
        "inspections/partials/recommandation_update.html",
        {"rec": rec, "form": form},
    )


@login_required
@require_GET
def recommandation_inline_read(request, pk):
    """
    HTMX view to read only a recommendation from the recommendations tab.
    Only fragment (recommandation_read.html).
    """
    rec = get_recommandation_by_id(pk, request.user)
    return render(
        request,
        "inspections/partials/recommandation_read.html",
        {"rec": rec},
    )


@login_required
@require_POST
def recommandation_archive(request, pk):
    rec = get_recommandation_by_id(pk, request.user)
    rec.archive(user=request.user)

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_recommandations_tab(request, rec.folder)

    return redirect("inspections:folder_detail", pk=rec.folder_id)


@login_required
@require_POST
def recommandation_unarchive(request, pk):
    rec = get_recommandation_by_id(pk, request.user)
    rec.unarchive(user=request.user)

    if request.headers.get("HX-Request"):
        # Re-render the current tab only, so the user stays on it
        return _render_recommandations_tab(request, rec.folder)

    return redirect("inspections:folder_detail", pk=rec.folder_id)



@login_required
@require_http_methods(["GET", "POST"])
def recommandation_delete(request, pk):
    """
    Permanently delete an archived recommendation.
    - GET  : Render the confirmation modal.
    - POST : Delete the recommendation and re-render the tab (409 if it is still active).
    """
    rec = get_recommandation_by_id(pk, request.user)

    if request.method == "GET":
        return _delete_modal(
            request, rec,
            title="Supprimer définitivement cette recommandation ?",
            label=f"REC-{rec.pk}",
            post_url=reverse("inspections:recommandation_delete", args=[rec.pk]),
            post_target="#tab-content",
            sections=[{"warning": True, "title": "Cette action est irréversible."}],
        )

    if rec.is_active:
        return HttpResponse("La recommandation doit être archivée avant d'être supprimée.", status=409)

    folder = rec.folder
    delete_archived_instance(rec)

    if request.headers.get("HX-Request"):
        return _render_recommandations_tab(request, folder)
    return redirect("inspections:folder_detail", pk=folder.pk)


# ==========================================
# ==== FOLDER TABS SECTION =================
# ==========================================

@login_required
@require_GET
def folder_tab_overview(request, pk):
    """Show only the content of the overview tab."""
    folder = get_inspection_folder_by_id(pk, request.user)
    return render(
        request,
        "inspections/partials/tab_overview.html",
        {"folder": folder},
    )


def _render_visit_tab(request, folder):
    """Render the visit tab content, including the latest visit and its sections."""
    latest_visit = folder.get_latest_visit
    context = {
        "folder": folder,
        "visit": latest_visit,
        "sections": [],
    }
    if latest_visit and latest_visit.template and latest_visit.template.schema:
        context["sections"] = latest_visit.template.schema.get("sections", [])

    return render(request, "inspections/partials/tab_visit.html", context)


@login_required
@require_GET
def folder_tab_visit(request, pk):
    """Open the content of the visit tab."""
    folder = get_inspection_folder_by_id(pk, request.user)
    return _render_visit_tab(request, folder)


def _render_recommandations_tab(request, folder):
    """Render the recommendations tab content."""
    return render(
        request,
        "inspections/partials/tab_recommandations.html",
        {
            "recommandations": folder.recommandations.select_related("created_by", "updated_by"),
            "active_count": folder.recommandations.filter(is_active=True).count(),
        },
    )


@login_required
@require_GET
def folder_tab_recommandations(request, pk):
    """Show only the content of the recommendations tab."""
    folder = get_inspection_folder_by_id(pk, request.user)
    return _render_recommandations_tab(request, folder)
