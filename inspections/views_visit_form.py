from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.decorators import htmx_login_required
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
def visit_form(request, pk):
    """Full page of the visit form, opened on ?section=<id> (first section by default)."""
    visit = get_visit_by_id(pk, request.user)
    context = build_form_context(visit, request.GET.get("section"))
    return render(request, "inspections/visit_form.html", context)


@htmx_login_required(redirect=False)
@require_GET
def visit_form_section(request, pk, section_id):
    """Fragment of one section (and the navigation, out of band), loaded when the inspector moves."""
    visit = get_visit_by_id(pk, request.user)
    context = build_form_context(visit, section_id)
    context["oob"] = True
    return render(request, "inspections/partials/visit/visit_form_body.html", context)


def _saved_context(visit, section_id, field_id, error=None):
    context = build_form_context(visit, section_id)
    context.update({"oob": True, "changed_field": field_id, "error": error})
    return context


@htmx_login_required(redirect=False)
@require_POST
def visit_save_answers(request, pk):
    """
    Save on the fly the answer of one field (posted as field_id + value).
    - 200 : saved, the answer is a set of out of band fragments (header, navigation, indicator).
    - 422 : invalid value, nothing saved, the message is shown under the field.
    - 409 : the visit is done or archived.
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
        message = e.field_errors[field_id] if isinstance(e, AnswersValidationError) else e.messages[0]
        return render(
            request,
            "inspections/partials/visit/visit_form_saved.html",
            _saved_context(visit, section_id, field_id, message),
            status=422,
        )

    return render(request, "inspections/partials/visit/visit_form_saved.html", _saved_context(visit, section_id, field_id))


@login_required
@require_POST
def visit_complete(request, pk):
    """
    End the filling. 422 re-renders the form on the first section with a missing required field,
    otherwise the inspector goes back to the visits of the folder. The visit is not marked as done by this.
    """
    visit = get_visit_by_id(pk, request.user)
    try:
        complete_visit(visit.pk, request.user)
    except VisitLockedError:
        return HttpResponse("La visite est archivée.", status=409)
    except AnswersValidationError as e:
        visit.refresh_from_db()
        context = build_form_context(visit, get_first_incomplete_section(visit), errors=e.field_errors)
        context["show_errors"] = True
        return render(request, "inspections/partials/visit/visit_form_page.html", context, status=422)

    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("inspections:folder_detail", args=[visit.folder_id]) + "?tab=visit"
    return response


@login_required
@require_POST
def visit_reopen(request, pk):
    visit = get_visit_by_id(pk, request.user)
    try:
        reopen_visit(visit, request.user)
    except VisitLockedError:
        raise Http404
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("inspections:visit_form", args=[visit.pk])
    return response
