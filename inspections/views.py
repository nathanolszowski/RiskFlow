from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from crm.models import Company
from inspections.forms import InspectionFolderForm
from core.services import create_tracked_instance
from inspections.models import InspectionFolder
from .services.inspectionfolder import get_inspection_folders_by_user, get_inspection_folder_by_id



def _filter_and_sort_folders(request):
    """Utility function to filter and sort inspection folders based on request parameters."""
    folders = get_inspection_folders_by_user(request.user)

    phase = request.GET.get('phase') or request.POST.get('phase', '').strip()
    if phase:
        folders = folders.filter(current_phase=phase)

    status = request.GET.get('status') or request.POST.get('status', '').strip()
    if status == 'active':
        folders = folders.filter(is_active=True)
    elif status == 'archived':
        folders = folders.filter(is_active=False)

    company_id = request.GET.get('company') or request.POST.get('company', '').strip()
    if company_id:
        folders = folders.filter(company_id=company_id)

    sort_by = request.GET.get('sort') or request.POST.get('sort', '-updated_at')
    allowed_sorts = ['-updated_at', '-created_at', 'reference', 'company__name']
    if sort_by not in allowed_sorts:
        sort_by = '-updated_at'

    return folders.order_by(sort_by)


@login_required
def folders_view(request):
    folders = _filter_and_sort_folders(request)
    
    companies = Company.objects.filter(
        inspection_folders__in=get_inspection_folders_by_user(request.user)
    ).distinct()
    
    context = {
        'folders': folders,
        'companies': companies,
        'selected_companies': request.GET.getlist('companies'),
        'phase_choices': InspectionFolder.Phase.choices,
    }
    return render(request, 'inspections/folders.html', context)

@login_required
def create_folder_htmx(request):
    """HTMX view to create a new inspection folder."""
    if request.method == 'POST':
        form = InspectionFolderForm(request.POST)
        if form.is_valid():
            create_tracked_instance(form, request.user)
            
            folders = _filter_and_sort_folders(request)
            
            response = render(request, 'inspections/partials/folder_grid.html', {'folders': folders})
            response['HX-Trigger'] = 'closeModal'
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
    latest_visit = folder.get_latest_visit  
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