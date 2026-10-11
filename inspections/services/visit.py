from django.shortcuts import get_object_or_404
from inspections.models import VisitInstance


def get_visit_by_id(pk, user):
    """
    Retrieves a specific visit instance by its primary key (pk)
    while ensuring that its inspection folder was created by the logged-in user.
    """
    return get_object_or_404(
        VisitInstance.objects.select_related('folder', 'template', 'created_by', 'updated_by'),
        pk=pk,
        folder__created_by=user
    )
