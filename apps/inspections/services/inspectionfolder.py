"""Services of the inspection folders, always restricted to the user who created them."""

from typing import TYPE_CHECKING

from core.services.geo import certify_address
from django.db.models import Q, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from inspections.models import InspectionFolder

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models import Model


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


def _filter_param(request: HttpRequest, name: str) -> str:
    """Return a filter of the folders list, read from GET then POST, without spaces.

    Args:
        request: Current request.
        name: Name of the parameter.

    Returns:
        The stripped value, empty when the parameter is missing.
    """
    return (request.GET.get(name) or request.POST.get(name) or "").strip()


def get_filtered_folders(request: HttpRequest) -> QuerySet:
    """Return the folders of the logged-in user, filtered and sorted by the request.

    Args:
        request: Current request. Reads, from GET or POST, ``q`` (search on
            reference and company name), ``phase``, ``status`` (``active`` or
            ``archived``), ``company`` (company id, ignored if not a number) and
            ``sort`` (``-updated_at``, ``-created_at``, ``reference`` or
            ``company__name``, anything else falls back to ``-updated_at``).

    Returns:
        The filtered and sorted folders.
    """
    folders = InspectionFolder.objects.filter(created_by=request.user)

    query = _filter_param(request, "q")
    if query:
        folders = folders.filter(
            Q(reference__icontains=query) | Q(company__name__icontains=query)
        )

    phase = _filter_param(request, "phase")
    if phase:
        folders = folders.filter(current_phase=phase)

    status = _filter_param(request, "status")
    if status == "active":
        folders = folders.filter(is_active=True)
    elif status == "archived":
        folders = folders.filter(is_active=False)

    company_id = _filter_param(request, "company")
    if company_id.isdigit():
        folders = folders.filter(company_id=company_id)

    sort_by = _filter_param(request, "sort")
    allowed_sorts = ["-updated_at", "-created_at", "reference", "company__name"]
    if sort_by not in allowed_sorts:
        sort_by = "-updated_at"

    return folders.order_by(sort_by)


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


def create_tracked_instance(form: ModelForm, user: "CustomUser") -> InspectionFolder:
    """Save a model form, setting ``created_by`` if it is empty.

    Unlike ``core.services.create_tracked_instance``, it also saves the
    many-to-many data and keeps an existing ``created_by``.

    Args:
        form: Valid model form.
        user: User recorded as ``created_by`` when the instance has none.

    Returns:
        The saved instance.
    """
    instance = form.save(commit=False)
    # Test the id: reading an unset ``created_by`` raises instead of returning None
    if not instance.created_by_id:
        instance.created_by = user
    instance.save()
    form.save_m2m()
    certify_address(instance)
    return instance
