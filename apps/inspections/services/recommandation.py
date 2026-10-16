from django.shortcuts import get_object_or_404

from inspections.models import Recommandation


def get_recommandation_by_id(pk, user):
    """
    Retrieves a specific recommendation by its primary key (pk)
    while ensuring that its inspection folder was created by the logged-in user.
    """
    return get_object_or_404(
        Recommandation.objects.select_related("folder", "created_by", "updated_by"),
        pk=pk,
        folder__created_by=user,
    )
