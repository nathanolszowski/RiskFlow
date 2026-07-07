from inspections.models import InspectionFolder
from django.shortcuts import get_object_or_404


def get_inspection_folders_by_user(user):
    """
    Retrieve all active inspection folders created by a specific user, along with their associated client information.
    """
    return InspectionFolder.objects.filter(
        created_by=user,
        is_active=True
    ).select_related("client")

def get_inspection_folder_by_id(folder_id, user):
    """
    Retrieve a specific inspection folder by its ID, ensuring it belongs to the specified user.
    """
    queryset = InspectionFolder.objects.filter(created_by=user, is_active=True)
    queryset = queryset.select_related('client')
    queryset = queryset.prefetch_related('recommandations')
    return get_object_or_404(queryset, id=folder_id)