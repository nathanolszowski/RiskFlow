
from inspections.models import InspectionFolder
from django.utils import timezone


def create_inspection_folder(form, user):
    """
    Crée un nouveau dossier d'inspection et l'associe à l'utilisateur créateur.
    """
    folder = form.save(commit=False)
    folder.created_by = user
    folder.updated_by = user
    folder.save()
    return folder


def get_inspection_folders_by_user(user):
    """
    Récupère tous les dossiers actifs créés par un utilisateur spécifique,
    en optimisant la requête pour le client lié.
    """
    return InspectionFolder.objects.filter(
        created_by=user,
        is_active=True
    ).select_related("client")


def update_inspection_folder(folder, user, **fields_to_update):
    """
    Update the specified fields of an inspection folder and set the updated_by field to the current user.
    """
    for field_name, value in fields_to_update.items():
        setattr(folder, field_name, value)
    folder.updated_by = user
    update_fields = list(fields_to_update.keys()) + ['updated_by', 'updated_at']
    folder.save(update_fields=update_fields)
    return folder


def archived_inspection_folder(folder, user):
    """
    Virtually archive a folder by marking it as inactive and setting the archived fields.
    """
    folder.is_active = False
    folder.archived_at = timezone.now()
    folder.archived_by = user
    folder.updated_by = user
    folder.save()
    return folder


def unarchive_inspection_folder(folder, user):
    """
    Unarchive a folder by marking it as active and clearing the archived fields.
    """
    folder.is_active = True
    folder.archived_at = None
    folder.archived_by = None
    folder.updated_by = user
    folder.save()
    return folder


def delete_inspection_folder(folder):
    """
    Hard delete a folder from the database. Use with caution, as this action is irreversible.
    """
    folder.delete()