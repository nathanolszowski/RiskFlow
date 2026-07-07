from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from inspections.forms import InspectionFolderForm
from core.services import create_tracked_instance
from services.inspectionfolder import get_inspection_folders_by_user



@login_required
def folders_view(request):
    folders = get_inspection_folders_by_user(request.user)

    return render(request, 'inspections/dossiers.html', {'folders': folders})

@login_required
def create_folder_htmx(request):
    """HTMX view to create a new inspection folder."""
    if request.method == 'POST':
        form = InspectionFolderForm(request.POST)
        if form.is_valid():
            create_tracked_instance(form, request.user)

            # Reload the list of folders after creation
            folders = get_inspection_folders_by_user(request.user)
            response = render(request, 'inspections/partials/folder_grid.html', {'folders': folders})
            response['HX-Trigger'] = 'closeModal' # Trigger to close the modal in HTMX
            return response
    else:
        form = InspectionFolderForm()
        
    return render(request, 'inspections/partials/folder_form_modal.html', {'form': form})