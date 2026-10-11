from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.core.paginator import Paginator
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
    """Vue HTMX pour créer un dossier d'inspection (depuis la liste ou la fiche Société)."""
    company_id = request.GET.get("company") or request.POST.get("company")
    selected_company = Company.objects.filter(pk=company_id).first() if company_id else None

    if request.method == "POST":
        form = InspectionFolderForm(request.POST)

        if selected_company:
            form.fields['contact'].queryset = Contact.objects.filter(company=selected_company)

        if form.is_valid():
            folder = create_tracked_instance(form, request.user)

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
        form.fields['contact'].queryset = Contact.objects.filter(company=selected_company)

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
@require_POST
def folder_archive(request, folder_id):
    folder = get_inspection_folder_by_id(folder_id, request.user)
    folder.is_active = False
    folder.save()

    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    return redirect("inspections:folder_detail", pk=folder.id)


@login_required
@require_POST
def folder_unarchive(request, folder_id):
    folder = get_inspection_folder_by_id(folder_id, request.user)
    folder.is_active = True
    folder.save()

    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    return redirect("inspections:folder_detail", pk=folder.id)

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


@login_required
@require_GET
def folder_tab_visit(request, pk):
    """Open the content of the visit tab, including the latest visit and its sections."""
    folder = get_inspection_folder_by_id(pk, request.user)
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
def folder_tab_recommandations(request, pk):
    """Show only the content of the recommendations tab."""
    folder = get_inspection_folder_by_id(pk, request.user)
    return render(
        request,
        "inspections/partials/tab_recommandations.html",
        {"recommandations": folder.recommandations.select_related("created_by", "updated_by")},)