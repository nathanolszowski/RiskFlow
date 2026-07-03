from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from inspections.models import InspectionFolder, InspectionFolderForm



@login_required
def folders_view(request):
    folders = InspectionFolder.objects.filter(
        created_by=request.user, 
        is_active=True
    ).select_related('client')
    
    return render(request, 'inspections/folders.html', {'folders': folders})

@login_required
def create_folder_htmx(request):
    """Gère l'affichage de la popup ET la création en HTMX"""
    if request.method == 'POST':
        form = InspectionFolderForm(request.POST)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.created_by = request.user
            folder.save()
            
            # Option HTMX : On recharge les dossiers en tâche de fond et on ferme la modal
            folders = InspectionFolder.objects.filter(created_by=request.user, is_active=True).select_related('client')
            response = render(request, 'inspections/partials/folder_grid.html', {'folders': folders})
            response['HX-Trigger'] = 'closeModal' # Déclenche un événement JS pour fermer la popup
            return response
    else:
        form = InspectionFolderForm()
        
    return render(request, 'inspections/partials/folder_form_modal.html', {'form': form})