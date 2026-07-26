from django.utils import timezone


def create_tracked_instance(form, user):
    """
    Create a new instance of a tracked model from a form, associating it with the user who created it.
    """
    instance = form.save(commit=False)
    instance.created_by = user
    instance.updated_by = user
    instance.save()
    return instance


def update_tracked_instance(instance, user, **fields_to_update):
    """
    Update a tracked instance with the provided fields and associate the update with the user.
    """
    for field_name, value in fields_to_update.items():
        setattr(instance, field_name, value)
    
    instance.updated_by = user
    
    # Force the update of the updated_by and updated_at fields
    update_fields = list(fields_to_update.keys()) + ['updated_by', 'updated_at']
    instance.save(update_fields=update_fields)
    return instance


def archive_tracked_instance(instance, user):
    """
    Archived a tracked instance, setting its active status to False and recording the archive metadata.
    """
    instance.is_active = False
    instance.archived_at = timezone.now()
    instance.archived_by = user
    instance.updated_by = user
    instance.save()
    return instance


def unarchive_tracked_instance(instance, user):
    """Unarchived a tracked instance, restoring its active status and clearing archive metadata.

    Args:
        instance (TrackingModel): The instance to unarchive.
        user (User): The user performing the unarchive action.

    Returns:
        TrackingModel: The unarchived instance.
    """
    instance.is_active = True
    instance.archived_at = None
    instance.archived_by = None
    instance.updated_by = user
    instance.save()
    return instance


def hard_delete_instance(instance):
    """
    Delete permanently any model instance. Use with caution, as this action is irreversible.
    """
    instance.delete()

def theme_processor(request):
    return {
        'current_theme': request.session.get('theme', 'dark')
    }