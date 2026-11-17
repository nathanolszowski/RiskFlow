"""Services of the recommendations, restricted to the owner of their folder."""

from typing import TYPE_CHECKING

from core.services import create_tracked_instance
from django.shortcuts import get_object_or_404

from inspections.models import InspectionFolder, Recommandation

if TYPE_CHECKING:
    from accounts.models import CustomUser

    from inspections.forms import RecommandationCreateForm


def get_recommandation_by_id(pk: int, user: "CustomUser") -> Recommandation:
    """Return a recommendation, ensuring that its folder was created by the user.

    Args:
        pk: Primary key of the recommendation.
        user: Logged-in user, who must own the folder.

    Returns:
        The recommendation, with its folder and tracking users.

    Raises:
        Http404: If the recommendation does not exist or its folder belongs to
            another user.
    """
    return get_object_or_404(
        Recommandation.objects.select_related("folder", "created_by", "updated_by"),
        pk=pk,
        folder__created_by=user,
    )


def create_recommandation(
    form: "RecommandationCreateForm", folder: InspectionFolder, user: "CustomUser"
) -> Recommandation:
    """Create a recommendation in a folder from a valid form.

    Args:
        form: Valid creation form.
        folder: Folder the recommendation belongs to.
        user: User creating the recommendation, who must own the folder.

    Returns:
        The saved recommendation, open by default.
    """
    form.instance.folder = folder
    return create_tracked_instance(form, user)
