"""Generic helpers for tracked models (create, update, delete) and template context.

Archiving goes through ``TrackingModel.archive()`` / ``unarchive()``, which run the
cascade of the model.
"""

from typing import TYPE_CHECKING, Any, TypeVar

from django.forms import ModelForm
from django.http import HttpRequest

from core.models import TrackingModel

if TYPE_CHECKING:
    from accounts.models import CustomUser

T = TypeVar("T", bound=TrackingModel)


def create_tracked_instance(form: ModelForm, user: "CustomUser") -> Any:
    """Create an instance of a tracked model from a valid form.

    Args:
        form: Valid model form of a ``TrackingModel`` subclass.
        user: User creating the instance, recorded as ``created_by`` and
            ``updated_by``.

    Returns:
        The saved instance, many-to-many data included.
    """
    instance = form.save(commit=False)
    instance.created_by = user
    instance.updated_by = user
    instance.save()
    form.save_m2m()
    return instance


def update_tracked_form(form: ModelForm, user: "CustomUser") -> Any:
    """Save a valid edit form of a tracked instance, recording who changed it.

    Args:
        form: Valid model form bound to an existing ``TrackingModel`` instance.
        user: User performing the update, recorded as ``updated_by``.

    Returns:
        The saved instance, many-to-many data included.
    """
    instance = form.save(commit=False)
    instance.updated_by = user
    instance.save()
    form.save_m2m()
    return instance


def update_tracked_instance(
    instance: T, user: "CustomUser", **fields_to_update: Any
) -> T:
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
