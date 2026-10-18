"""Shared modals of the apps."""

from typing import Any, Optional

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from core.models import TrackingModel


def delete_confirm_modal(
    request: HttpRequest,
    obj: TrackingModel,
    *,
    title: str,
    label: str,
    post_url: str,
    sections: list[dict[str, Any]],
    post_target: Optional[str] = None,
) -> HttpResponse:
    """Render the permanent-deletion modal.

    It only offers the confirmation once the object is archived.

    Args:
        request: Current request.
        obj: Object to delete.
        title: Title of the modal.
        label: Name of the object shown in the modal.
        post_url: URL the confirmation is posted to.
        sections: Sections of the modal (``title``, ``entries``, ``note``, ``warning``).
        post_target: HTMX target of the confirmation, if not the default one.

    Returns:
        The modal (``archive_confirm_modal.html``), without confirmation button while
        the object is still active.
    """
    blocking = None
    if obj.is_active:
        blocking = {
            "title": "Suppression impossible : cet élément n'est pas archivé.",
            "note": "Archivez-le d'abord, puis supprimez-le.",
        }
    return render(
        request,
        "core/partials/modal/archive_confirm_modal.html",
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
