"""Shared confirmation modals of the apps (``archive_confirm_modal.html``)."""

from typing import Any, Optional

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from core.models import TrackingModel

TEMPLATE = "core/partials/modal/archive_confirm_modal.html"


def confirm_modal(
    request: HttpRequest,
    *,
    title: str,
    label: str,
    post_url: str,
    sections: Optional[list[dict[str, Any]]] = None,
    blocking: Optional[dict[str, Any]] = None,
    post_target: Optional[str] = None,
) -> HttpResponse:
    """Render the archiving confirmation modal.

    Args:
        request: Current request.
        title: Title of the modal.
        label: Name of the object shown in the modal.
        post_url: URL the confirmation is posted to.
        sections: Sections of the modal (``title``, ``entries``, ``note``, ``warning``).
        blocking: Reason the action is refused (``title``, ``entries``, ``note``): the
            confirmation button is then hidden.
        post_target: HTMX target of the confirmation, if not the default one.

    Returns:
        The modal.
    """
    return render(
        request,
        TEMPLATE,
        {
            "title": title,
            "object_label": label,
            "post_url": post_url,
            "post_target": post_target,
            "blocking": blocking,
            "sections": sections or [],
        },
    )


def delete_confirm_modal(
    request: HttpRequest,
    obj: TrackingModel,
    *,
    title: str,
    label: str,
    post_url: str,
    sections: list[dict[str, Any]],
    post_target: Optional[str] = None,
    blocking: Optional[dict[str, Any]] = None,
) -> HttpResponse:
    """Render the permanent-deletion modal.

    It only offers the confirmation once the object is archived and nothing else
    blocks the deletion.

    Args:
        request: Current request.
        obj: Object to delete.
        title: Title of the modal.
        label: Name of the object shown in the modal.
        post_url: URL the confirmation is posted to.
        sections: Sections of the modal (``title``, ``entries``, ``note``, ``warning``).
        post_target: HTMX target of the confirmation, if not the default one.
        blocking: Another reason the deletion is refused (``title``, ``entries``,
            ``note``), used when the object is archived.

    Returns:
        The modal (``archive_confirm_modal.html``), without confirmation button while
        the object is still active or ``blocking`` is given.
    """
    if obj.is_active:
        blocking = not_archived_blocking()
    return render(
        request,
        TEMPLATE,
        {
            "title": title,
            "object_label": label,
            "action_verb": "supprimer définitivement",
            "confirm_label": "Supprimer définitivement",
            "danger": True,
            "post_url": post_url,
            "post_target": post_target,
            "blocking": blocking,
            "sections": sections,
        },
    )


def not_archived_blocking() -> dict[str, str]:
    """Return the blocking message of a deletion asked on an active object."""
    return {
        "title": "Suppression impossible : cet élément n'est pas archivé.",
        "note": "Archivez-le d'abord, puis supprimez-le.",
    }
