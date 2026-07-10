from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from inspections.forms import InspectionFolderForm
from core.services import create_tracked_instance
from .services.inspectionfolder import get_inspection_folders_by_user, get_inspection_folder_by_id



@login_required
def folders_view(request):
    folders = get_inspection_folders_by_user(request.user)

    return render(request, 'inspections/folders.html', {'folders': folders})

@login_required
def create_folder_htmx(request):
    """HTMX view to create a new inspection folder."""
    if request.method == 'POST':
        form = InspectionFolderForm(request.POST)
        if form.is_valid():
            create_tracked_instance(form, request.user)

            folders = get_inspection_folders_by_user(request.user)
            response = render(request, 'inspections/partials/folder_grid.html', {'folders': folders})
            response['HX-Trigger'] = 'closeModal' # Trigger to close the modal in HTMX
            return response
    else:
        form = InspectionFolderForm()
        
    return render(request, 'inspections/partials/folder_form_modal.html', {'form': form})

@login_required
def folder_detail_view(request, folder_id):
    """Show the default details of a specific inspection folder."""
    folder = get_inspection_folder_by_id(folder_id, request.user)
    return render(request, 'inspections/folder_detail.html', {'folder': folder})

@login_required
def folder_tab_overview(request, folder_id):
    """Show only the content of the overview tab."""
    folder = get_inspection_folder_by_id(folder_id, request.user)
    
    return render(request, 'inspections/partials/tab_overview.html', {'folder': folder,})

@login_required
def folder_tab_visit(request, folder_id):
    """
    Open the content of the visit tab, including the latest visit and its sections.
    """
    folder = get_inspection_folder_by_id(folder_id, request.user)
    latest_visit = folder.visits.select_related('template').first()
    context = {
        'folder': folder,
        'visit': latest_visit,
        'sections': []
    }
    if latest_visit and latest_visit.template and latest_visit.template.schema:
        context['sections'] = latest_visit.template.schema.get('sections', [])
        
    return render(request, 'inspections/partials/tab_visit.html', context)

@login_required
def folder_tab_recommandations(request, folder_id):
    """Show only the content of the recommendations tab."""
    folder = get_inspection_folder_by_id(folder_id, request.user)
    return render(request, 'inspections/partials/tab_recommandations.html', {'recommandations': folder.recommandations.all()})