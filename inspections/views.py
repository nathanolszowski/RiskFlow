from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_http_methods
from django.core.paginator import Paginator
from django.http import HttpResponse
from .forms import InspectionFolderForm
from .models import InspectionFolder
from crm.models import Company
from inspections.services.inspectionfolder import get_filtered_folders, get_inspection_folder_by_id, create_tracked_instance


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
    """HTMX view to render and process the creation form for inspection folders."""
    company_id = request.GET.get("company") or request.POST.get("company")

    if request.method == "POST":
        form = InspectionFolderForm(request.POST)
        if form.is_valid():
            folder = create_tracked_instance(form, request.user)

            if company_id:
                response = HttpResponse(status=204)
                response["HX-Refresh"] = "true"
                return response

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
                {"form": form},
                status=422,
            )

    initial_data = {}
    if company_id:
        initial_data["company"] = company_id

    form = InspectionFolderForm(initial=initial_data)
    return render(
        request, "inspections/partials/folder_form_modal.html", {"form": form}
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
        {"recommandations": folder.recommandations.all()},)