"""Generic helpers for tracked models (create, update, archive, delete) and template context."""

from typing import TYPE_CHECKING, Any

from django.forms import ModelForm
from django.http import HttpRequest
from django.utils import timezone

from core.models import TrackingModel

if TYPE_CHECKING:
    from accounts.models import CustomUser


def create_tracked_instance(form: ModelForm, user: "CustomUser") -> TrackingModel:
    """Create an instance of a tracked model from a valid form.

    Args:
        form: Valid model form of a ``TrackingModel`` subclass.
        user: User creating the instance, recorded as ``created_by`` and
            ``updated_by``.

    Returns:
        The saved instance.
    """
    instance = form.save(commit=False)
    instance.created_by = user
    instance.updated_by = user
    instance.save()
    return instance


def update_tracked_instance(
    instance: TrackingModel, user: "CustomUser", **fields_to_update: Any
) -> TrackingModel:
    """Update a tracked instance with the provided fields.

    Only these fields, ``updated_by`` and ``updated_at`` are written to the
    database.

    Args:
        instance: Instance to update.
        user: User performing the update, recorded as ``updated_by``.
        **fields_to_update: New values, by field name.

    Returns:
        The updated instance.
    """
    for field_name, value in fields_to_update.items():
        setattr(instance, field_name, value)

    instance.updated_by = user

    # Force the update of the updated_by and updated_at fields
    update_fields = list(fields_to_update.keys()) + ["updated_by", "updated_at"]
    instance.save(update_fields=update_fields)
    return instance


def archive_tracked_instance(
    instance: TrackingModel, user: "CustomUser"
) -> TrackingModel:
    """Archive a tracked instance, without cascading to its related records.

    Sets ``is_active`` to False and records the archive date and user.

    Args:
        instance: Instance to archive.
        user: User performing the action.

    Returns:
        The archived instance.
    """
    instance.is_active = False
    instance.archived_at = timezone.now()
    instance.archived_by = user
    instance.updated_by = user
    instance.save()
    return instance


def unarchive_tracked_instance(
    instance: TrackingModel, user: "CustomUser"
) -> TrackingModel:
    """Unarchive a tracked instance, without cascading to its related records.

    Restores ``is_active`` and clears the archive date and user.

    Args:
        instance: Instance to unarchive.
        user: User performing the action.

    Returns:
        The unarchived instance.
    """
    instance.is_active = True
    instance.archived_at = None
    instance.archived_by = None
    instance.updated_by = user
    instance.save()
    return instance


def hard_delete_instance(instance: Any) -> None:
    """Delete permanently any model instance.

    Use with caution, as this action is irreversible. For tracked models, prefer
    ``delete_archived_instance()``.

    Args:
        instance: Model instance to delete.
    """
    instance.delete()


def delete_archived_instance(instance: TrackingModel) -> None:
    """Delete permanently a tracked instance, only if it has been archived first.

    Args:
        instance: Archived instance to delete.

    Raises:
        ValueError: If the instance is still active.
    """
    if instance.is_active:
        raise ValueError("Only an archived object can be deleted permanently.")
    hard_delete_instance(instance)


def theme_processor(request: HttpRequest) -> dict[str, str]:
    """Template context processor exposing the theme stored in the session.

    Args:
        request: Current request.

    Returns:
        A dict with ``current_theme`` (``"dark"`` by default).
    """
    return {"current_theme": request.session.get("theme", "dark")}
