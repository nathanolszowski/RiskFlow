"""Services of the inspection folders, always restricted to the user who created them."""

from typing import TYPE_CHECKING

from core.services import create_tracked_instance, update_tracked_form
from core.services.geo import certify_address
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404

from inspections.models import InspectionFolder

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models import Model

    from inspections.forms import InspectionFolderForm, InspectionFolderUpdateForm


def get_inspection_folders_by_user(user: "CustomUser") -> QuerySet:
    """Return the active folders created by the user, with their company.

    Args:
        user: Owner of the folders.

    Returns:
        The active folders, company already loaded.
    """
    return InspectionFolder.objects.filter(
        created_by=user, is_active=True
    ).select_related("company")


def get_company_folders(company: "Model", user: "CustomUser") -> QuerySet:
    """Return every folder (active or archived) of a company created by the user.

    Args:
        company: Company of the folders.
        user: Owner of the folders.

    Returns:
        The folders, newest first.
    """
    return InspectionFolder.objects.filter(
        company=company,
        created_by=user,
    ).order_by("-created_at")


def get_filtered_folders(
    user: "CustomUser",
    *,
    q: str = "",
    phase: str = "",
    status: str = "",
    company: str = "",
    sort: str = "",
) -> QuerySet:
    """Return the folders of the user, filtered and sorted.

    Args:
        user: Owner of the folders: the folders of the others never appear.
        q: Search on reference and company name.
        phase: Phase of the folders (``InspectionFolder.Phase``), all if empty.
        status: ``active`` or ``archived``, all for any other value.
        company: Company id, ignored if not a number.
        sort: ``-updated_at`` (default), ``-created_at``, ``reference`` or
            ``company__name``; anything else falls back to ``-updated_at``.

    Returns:
        The filtered and sorted folders.
    """
    q, phase, status = q.strip(), phase.strip(), status.strip()
    company = str(company).strip()

    folders = InspectionFolder.objects.filter(created_by=user)
    if q:
        folders = folders.filter(
            Q(reference__icontains=q) | Q(company__name__icontains=q)
        )
    if phase:
        folders = folders.filter(current_phase=phase)
    if status == "active":
        folders = folders.filter(is_active=True)
    elif status == "archived":
        folders = folders.filter(is_active=False)
    if company.isdigit():
        folders = folders.filter(company_id=company)

    allowed_sorts = ["-updated_at", "-created_at", "reference", "company__name"]
    return folders.order_by(sort if sort in allowed_sorts else "-updated_at")


def get_inspection_folder_by_id(pk: int, user: "CustomUser") -> InspectionFolder:
    """Return a folder, ensuring that it was created by the user.

    Args:
        pk: Primary key of the folder.
        user: Logged-in user, who must own the folder.

    Returns:
        The folder, with its company, contact and tracking users.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    return get_object_or_404(
        InspectionFolder.objects.select_related(
            "company", "contact", "created_by", "updated_by", "archived_by"
        ),
        pk=pk,
        created_by=user,
    )


def create_folder(form: "InspectionFolderForm", user: "CustomUser") -> InspectionFolder:
    """Create a folder of the user from a valid form and certify the site address.

    Args:
        form: Valid creation form.
        user: User creating the folder, who becomes its owner.

    Returns:
        The folder.
    """
    folder = create_tracked_instance(form, user)
    certify_address(folder)
    return folder


def update_folder(
    form: "InspectionFolderUpdateForm", user: "CustomUser"
) -> InspectionFolder:
    """Save a valid edit form of a folder and certify the site address again if needed.

    Args:
        form: Valid edit form.
        user: User editing the folder.

    Returns:
        The folder.
    """
    folder = update_tracked_form(form, user)
    certify_address(folder)
    return folder
