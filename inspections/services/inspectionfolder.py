from inspections.models import InspectionFolder


def get_inspection_folders_by_user(user):
    """
    Récupère tous les dossiers actifs créés par un utilisateur spécifique,
    en optimisant la requête pour le client lié.
    """
    return InspectionFolder.objects.filter(
        created_by=user,
        is_active=True
    ).select_related("client")