from inspections.models import InspectionFolder
from django.shortcuts import get_object_or_404
from django.db.models import Q


def get_inspection_folders_by_user(user):
    """
    Retrieve all active inspection folders created by a specific user, along with their associated client information.
    """
    return InspectionFolder.objects.filter(
        created_by=user,
        is_active=True
    ).select_related("company")

def get_filtered_folders(request):
    """
    Filters and sorts inspection records based on the parameters 
    provided in the GET or POST request.
    """
    # 1. Base Queryset : created_by authorization
    folders = InspectionFolder.objects.filter(created_by=request.user)

    # Global search
    query = request.GET.get('q') or request.POST.get('q', '').strip()
    if query:
        folders = folders.filter(
            Q(reference__icontains=query) |
            Q(company__name__icontains=query)
        )

    # Filter by phase
    phase = request.GET.get('phase') or request.POST.get('phase', '').strip()
    if phase:
        folders = folders.filter(current_phase=phase)

    # Filter by status
    status = request.GET.get('status') or request.POST.get('status', '').strip()
    if status == 'active':
        folders = folders.filter(is_active=True)
    elif status == 'archived':
        folders = folders.filter(is_active=False)

    # Filtre par Entreprise / Client
    company_id = request.GET.get('company') or request.POST.get('company', '').strip()
    if company_id:
        folders = folders.filter(company_id=company_id)

    # Sort results
    sort_by = request.GET.get('sort') or request.POST.get('sort', '-updated_at')
    allowed_sorts = ['-updated_at', '-created_at', 'reference', 'company__name']
    if sort_by not in allowed_sorts:
        sort_by = '-updated_at'

    return folders.order_by(sort_by)


def get_inspection_folder_by_id(pk, user):
    """
    Retrieves a specific inspection record by its primary key (pk)
    while ensuring that it was created by the logged-in user.
    """
    return get_object_or_404(
        InspectionFolder.objects.select_related('company', 'created_by'),
        pk=pk,
        created_by=user
    )


def create_tracked_instance(form, user):
    """
    Sauve a ModelForm with created_by user
    """
    instance = form.save(commit=False)
    if hasattr(instance, 'created_by') and not instance.created_by_id:
        instance.created_by = user
    instance.save()
    form.save_m2m()
    return instance