from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone

from inspections.models import VisitInstance
from inspections.validators import (
    validate_answers,
    compute_progress,
    iter_schema_fields,
)


class VisitLockedError(Exception):
    """The visit cannot be changed any more (done or archived)."""


def get_visit_by_id(pk, user):
    """
    Retrieves a specific visit instance by its primary key (pk)
    while ensuring that its inspection folder was created by the logged-in user.
    """
    return get_object_or_404(
        VisitInstance.objects.select_related(
            "folder", "template", "created_by", "updated_by"
        ),
        pk=pk,
        folder__created_by=user,
    )


def get_visits_for_folder(folder, status="active"):
    """Visits of a folder: active ones by default, archived ones with status='archived'."""
    visits = folder.visits.select_related("template", "created_by", "updated_by")
    visits = visits.filter(is_active=(status != "archived"))
    return visits.order_by(F("due_date").desc(nulls_last=True), "-created_at")


def get_next_visit(folder):
    """The visit to do next: the active, not yet done visit with the earliest date."""
    return (
        folder.visits.filter(is_active=True)
        .exclude(current_status=VisitInstance.Status.VALIDATED)
        .order_by(F("due_date").asc(nulls_last=True), "created_at")
        .first()
    )


def create_visit(folder, template, due_date, user):
    """
    Create a visit from a template. The structure of the template is frozen in the visit (snapshot),
    so the visit does not depend on the template afterwards.
    """
    if not template.is_active:
        raise ValidationError(
            "Ce template est archivé : il ne peut plus servir à préparer une visite."
        )
    if template.created_by_id != user.pk and not template.shared:
        raise ValidationError("Ce template n'est pas disponible.")

    visit = VisitInstance(
        folder=folder,
        template=template,
        due_date=due_date,
        data={"answers": {}},
        created_by=user,
        updated_by=user,
    )
    visit.snapshot_template()
    visit.save()
    return visit


def save_answers(visit_id, user, changes):
    """
    Save one or several answers of a visit ({field_id: value}, an empty value removes the answer).
    Called on the fly while the inspector fills the form, so it only touches the answers it receives:
    concurrent saves of different fields never overwrite each other. Required fields are not enforced here.
    Raise VisitLockedError (done or archived visit) or AnswersValidationError (invalid value).
    Return the visit with its up to date progress.
    """
    with transaction.atomic():
        visit = VisitInstance.objects.select_for_update().get(pk=visit_id)
        if (
            not visit.is_active
            or visit.current_status == VisitInstance.Status.VALIDATED
        ):
            raise VisitLockedError()

        cleaned = validate_answers(visit.instance_schema, changes)
        answers = dict(visit.answers)
        for field_id, value in changes.items():
            if field_id in cleaned:
                answers[field_id] = cleaned[field_id]
            else:
                answers.pop(field_id, None)

        visit.data = {**visit.data, "answers": answers}
        visit.revision += 1
        visit.updated_by = user
        visit.save(update_fields=["data", "revision", "updated_by", "updated_at"])
    return visit


def complete_visit(visit_id, user):
    """
    Check the visit at the end of the filling: every required field must be answered, otherwise
    AnswersValidationError is raised with the fields to fix. The status is not changed: the visit is only
    marked as done by the "done" checkbox of its planning (set_visit_done).
    """
    with transaction.atomic():
        visit = VisitInstance.objects.select_for_update().get(pk=visit_id)
        if not visit.is_active:
            raise VisitLockedError()
        validate_answers(visit.instance_schema, visit.answers, strict=True)
    return visit


def set_visit_done(visit, user, done):
    """
    Tick or untick a visit as done from its planning. Unlike complete_visit, required fields are not enforced
    (the visit can have been filled elsewhere). Unticked, the visit is planned again (late once its date is over).
    """
    if not visit.is_active:
        raise VisitLockedError()
    if done:
        if visit.current_status != VisitInstance.Status.VALIDATED:
            visit.current_status = VisitInstance.Status.VALIDATED
            visit.completed_at = timezone.now()
    elif visit.current_status == VisitInstance.Status.VALIDATED:
        visit.current_status = VisitInstance.Status.SCHEDULED
        visit.completed_at = None
    visit.updated_by = user
    visit.save(
        update_fields=["current_status", "completed_at", "updated_by", "updated_at"]
    )
    return visit


def reopen_visit(visit, user):
    """Make a done visit editable again."""
    if not visit.is_active:
        raise VisitLockedError()
    visit.current_status = VisitInstance.Status.SCHEDULED
    visit.completed_at = None
    visit.updated_by = user
    visit.save(
        update_fields=["current_status", "completed_at", "updated_by", "updated_at"]
    )
    return visit


def get_first_incomplete_section(visit):
    """Id of the first section that still has a required field to answer, or None."""
    for section in compute_progress(visit.instance_schema, visit.answers)["by_section"]:
        if section["missing_required"]:
            return section["id"]
    return None


def coerce_input(field, raw):
    """
    Convert the raw string posted by the form into the JSON value of the field.
    An empty string means "no answer". Raise ValidationError when the string cannot be read.
    """
    if raw is None or raw == "":
        return None
    field_type = field.get("type")
    if field_type == "boolean":
        if raw not in ("true", "false"):
            raise ValidationError("Réponse attendue : oui ou non.")
        return raw == "true"
    if field_type == "number":
        try:
            number = float(str(raw).replace(",", "."))
        except ValueError:
            raise ValidationError("Un nombre est attendu.")
        return int(number) if number.is_integer() else number
    return raw


def get_form_field(visit, field_id):
    for _, field in iter_schema_fields(visit.instance_schema):
        if field["id"] == field_id:
            return field
    return None


def build_form_context(visit, section_id=None, errors=None):
    """
    Everything the visit form needs: progress, navigation, and the fields of the current section
    with their answer and error. The structure comes from the snapshot of the visit, never from the template.
    """
    errors = errors or {}
    progress = visit.progress
    sections = sorted(
        visit.instance_schema.get("sections", []), key=lambda s: s.get("order", 0)
    )
    ids = [s["id"] for s in sections]
    index = ids.index(section_id) if section_id in ids else 0
    section = sections[index] if sections else {"id": "", "title": "", "fields": []}

    answers = visit.answers
    fields = []
    for field in sorted(section.get("fields", []), key=lambda f: f.get("order", 0)):
        value = answers.get(field["id"])
        fields.append(
            {
                **field,
                "required": field.get("required", True),
                "options": field.get("options") or [],
                "unit": field.get("unit") or "",
                "step": field.get("step"),
                "min": field.get("min"),
                "max": field.get("max"),
                "value": value,
                "value_display": "" if value is None else str(value).replace(".", ","),
                "error": errors.get(field["id"]),
            }
        )

    nav = []
    for item, summary in zip(sections, progress["by_section"]):
        nav.append(
            {**summary, "number": len(nav) + 1, "current": item["id"] == section["id"]}
        )

    return {
        "visit": visit,
        "progress": progress,
        "nav": nav,
        "section": section,
        "section_number": index + 1,
        "section_count": len(sections),
        "fields": fields,
        "previous_section_id": ids[index - 1] if index > 0 else None,
        "next_section_id": ids[index + 1] if index + 1 < len(ids) else None,
        "yes_no": [("true", "Oui"), ("false", "Non")],
        "readonly": (not visit.is_active)
        or visit.current_status == VisitInstance.Status.VALIDATED,
    }
