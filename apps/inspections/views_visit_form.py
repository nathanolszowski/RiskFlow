"""Views of the visit form: filling on the field, with answers saved on the fly."""

from typing import Any, Optional

from core.decorators import htmx_login_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from inspections.models import VisitInstance
from inspections.services.visit import (
    VisitLockedError,
    build_form_context,
    coerce_input,
    complete_visit,
    get_first_incomplete_section,
    get_form_field,
    get_visit_by_id,
    reopen_visit,
    save_answers,
)
from inspections.validators import AnswersValidationError

# ==========================================
# ==== VISIT FORM (FILLING ON THE FIELD) ===
# ==========================================


@login_required
@require_GET
def visit_form(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the full page of the visit form.

    Args:
        request: Current request. The ``section`` GET parameter is the id of the
            section to open (the first one by default).
        pk: Primary key of the visit.

    Returns:
        The full page.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, request.user)
    context = build_form_context(visit, request.GET.get("section"))
    return render(request, "inspections/visit_form.html", context)


@htmx_login_required(redirect=False)
@require_GET
def visit_form_section(request: HttpRequest, pk: int, section_id: str) -> HttpResponse:
    """Render one section, with the navigation out of band (HTMX).

    Loaded when the inspector moves to another section.

    Args:
        request: Current request.
        pk: Primary key of the visit.
        section_id: Id of the section to show.

    Returns:
        The section fragment.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, request.user)
    context = build_form_context(visit, section_id)
    context["oob"] = True
    return render(request, "inspections/partials/visit/visit_form_body.html", context)


def _saved_context(
    visit: VisitInstance,
    section_id: Optional[str],
    field_id: str,
    error: Optional[str] = None,
) -> dict[str, Any]:
    """Build the context of the fragments answered after saving a field.

    Args:
        visit: Visit being filled.
        section_id: Id of the section displayed.
        field_id: Id of the field that was saved.
        error: Error message to show under the field, if any.

    Returns:
        The form context, with ``oob``, ``changed_field`` and ``error`` added.
    """
    context = build_form_context(visit, section_id)
    context.update({"oob": True, "changed_field": field_id, "error": error})
    return context


@htmx_login_required(redirect=False)
@require_POST
def visit_save_answers(request: HttpRequest, pk: int) -> HttpResponse:
    """Save on the fly the answer of one field (HTMX).

    The field is posted as ``field_id`` and ``value``, with the current
    ``section_id``. Unauthenticated requests get a 401 without redirect.

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        - 200: saved, a set of out of band fragments (header, navigation, indicator).
        - 404: unknown field.
        - 409: the visit is done or archived.
        - 422: invalid value, nothing saved, the message is shown under the field.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, request.user)
    field_id = request.POST.get("field_id", "")
    section_id = request.POST.get("section_id")
    field = get_form_field(visit, field_id)
    if field is None:
        return HttpResponse("Champ inconnu.", status=404)

    try:
        value = coerce_input(field, request.POST.get("value"))
        visit = save_answers(visit.pk, request.user, {field_id: value})
    except VisitLockedError:
        return HttpResponse("La visite est terminée ou archivée.", status=409)
    except ValidationError as e:
        message = (
            e.field_errors[field_id]
            if isinstance(e, AnswersValidationError)
            else e.messages[0]
        )
        return render(
            request,
            "inspections/partials/visit/visit_form_saved.html",
            _saved_context(visit, section_id, field_id, message),
            status=422,
        )

    return render(
        request,
        "inspections/partials/visit/visit_form_saved.html",
        _saved_context(visit, section_id, field_id),
    )


@login_required
@require_POST
def visit_complete(request: HttpRequest, pk: int) -> HttpResponse:
    """End the filling of a visit.

    The visit is not marked as done by this: only its required fields are checked.

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        A 204 with ``HX-Redirect`` to the visits of the folder, a 409 if the visit is
        archived, or a 422 that re-renders the form on the first section with a
        missing required field.

    Raises:
        Http404: If the visit does not exist or belongs to another user.
    """
    visit = get_visit_by_id(pk, request.user)
    try:
        complete_visit(visit.pk, request.user)
    except VisitLockedError:
        return HttpResponse("La visite est archivée.", status=409)
    except AnswersValidationError as e:
        visit.refresh_from_db()
        context = build_form_context(
            visit, get_first_incomplete_section(visit), errors=e.field_errors
        )
        context["show_errors"] = True
        return render(
            request,
            "inspections/partials/visit/visit_form_page.html",
            context,
            status=422,
        )

    response = HttpResponse(status=204)
    response["HX-Redirect"] = (
        reverse("inspections:folder_detail", args=[visit.folder_id]) + "?tab=visit"
    )
    return response


@login_required
@require_POST
def visit_reopen(request: HttpRequest, pk: int) -> HttpResponse:
    """Make a done visit editable again and open its form.

    Args:
        request: Current request.
        pk: Primary key of the visit.

    Returns:
        A 204 with ``HX-Redirect`` to the visit form.

    Raises:
        Http404: If the visit does not exist, belongs to another user or is archived.
    """
    visit = get_visit_by_id(pk, request.user)
    try:
        reopen_visit(visit, request.user)
    except VisitLockedError:
        raise Http404
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("inspections:visit_form", args=[visit.pk])
    return response
