"""Services of the visits: creation, on-the-fly saving of answers, completion and form context.

The form, the progress and the validation only read ``VisitInstance.instance_schema``,
the snapshot of the template, never the template itself.
"""

import math
from datetime import date, time
from typing import TYPE_CHECKING, Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from inspections.models import InspectionFolder, VisitInstance, VisitTemplate
from inspections.validators import (
    compute_progress,
    iter_schema_fields,
    validate_answers,
)

if TYPE_CHECKING:
    from accounts.models import CustomUser


class VisitLockedError(Exception):
    """The visit cannot be changed any more (done or archived).

    Answered with a 409 by the views.
    """


def get_visit_by_id(pk: int, user: "CustomUser") -> VisitInstance:
    """Return a visit, ensuring that its folder was created by the user.

    Args:
        pk: Primary key of the visit.
        user: Logged-in user, who must own the folder.

    Returns:
        The visit, with its folder, template and tracking users.

    Raises:
        Http404: If the visit does not exist or its folder belongs to another user.
    """
    return get_object_or_404(
        VisitInstance.objects.select_related(
            "folder", "template", "created_by", "updated_by"
        ),
        pk=pk,
        folder__created_by=user,
    )


def get_visits_for_folder(folder: InspectionFolder, status: str = "active") -> QuerySet:
    """Return the visits of a folder, by date then by creation (newest first).

    Args:
        folder: Folder of the visits.
        status: ``"active"`` for the active visits, ``"archived"`` for the archived ones.

    Returns:
        The visits, those without a date last.
    """
    visits = folder.visits.select_related("template", "created_by", "updated_by")
    visits = visits.filter(is_active=(status != "archived"))
    return visits.order_by(
        F("due_date").desc(nulls_last=True),
        F("due_time").desc(nulls_last=True),
        "-created_at",
    )


def get_next_visit(folder: InspectionFolder) -> Optional[VisitInstance]:
    """Return the visit to do next: the active, not yet done visit with the earliest date.

    Args:
        folder: Folder of the visits.

    Returns:
        The visit, or None if there is none.
    """
    return (
        folder.visits.filter(is_active=True)
        .exclude(current_status=VisitInstance.Status.VALIDATED)
        .order_by(
            F("due_date").asc(nulls_last=True),
            F("due_time").asc(nulls_last=True),
            "created_at",
        )
        .first()
    )


def create_visit(
    folder: InspectionFolder,
    template: VisitTemplate,
    due_date: Optional[date],
    user: "CustomUser",
    due_time: Optional[time] = None,
) -> VisitInstance:
    """Create a visit from a template.

    The structure of the template is frozen in the visit (snapshot), so the visit
    does not depend on the template afterwards.

    Args:
        folder: Folder the visit belongs to.
        template: Template to start from.
        due_date: Planned date, if any.
        user: User creating the visit.
        due_time: Appointment time, if any.

    Returns:
        The saved visit.

    Raises:
        django.core.exceptions.ValidationError: If the template is archived, or
            neither owned by the user nor shared.
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
        due_time=due_time,
        data={"answers": {}},
        created_by=user,
        updated_by=user,
    )
    visit.snapshot_template()
    visit.save()
    return visit


def save_answers(
    visit_id: int, user: "CustomUser", changes: dict[str, Any]
) -> VisitInstance:
    """Save one or several answers of a visit.

    Called on the fly while the inspector fills the form, so it only touches the
    answers it receives: concurrent saves of different fields never overwrite each
    other. The visit row is locked during the save. Required fields are not enforced
    here, and the ``revision`` counter is incremented.

    Args:
        visit_id: Primary key of the visit.
        user: User saving the answers.
        changes: New answers, ``{field_id: value}``. An empty value removes the answer.

    Returns:
        The visit, with its up to date progress.

    Raises:
        VisitLockedError: If the visit is done or archived.
        AnswersValidationError: If a value is invalid.
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


def complete_visit(visit_id: int, user: "CustomUser") -> VisitInstance:
    """Check the visit at the end of the filling.

    Every required field must be answered. The status is not changed: the visit is
    only marked as done by the "done" checkbox of its planning (``set_visit_done``).

    Args:
        visit_id: Primary key of the visit.
        user: User finishing the visit.

    Returns:
        The visit.

    Raises:
        VisitLockedError: If the visit is archived.
        AnswersValidationError: With the fields to fix, if a required field is
            not answered.
    """
    with transaction.atomic():
        visit = VisitInstance.objects.select_for_update().get(pk=visit_id)
        if not visit.is_active:
            raise VisitLockedError()
        validate_answers(visit.instance_schema, visit.answers, strict=True)
    return visit


def set_visit_done(
    visit: VisitInstance, user: "CustomUser", done: bool
) -> VisitInstance:
    """Tick or untick a visit as done from its planning.

    Unlike ``complete_visit``, required fields are not enforced (the visit can have
    been filled elsewhere). Unticked, the visit is planned again (late once its
    date is over).

    Args:
        visit: Visit to update.
        user: User performing the action.
        done: True to mark the visit as done, False to plan it again.

    Returns:
        The updated visit.

    Raises:
        VisitLockedError: If the visit is archived.
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


def reopen_visit(visit: VisitInstance, user: "CustomUser") -> VisitInstance:
    """Make a done visit editable again, by planning it again.

    Args:
        visit: Visit to reopen.
        user: User performing the action.

    Returns:
        The updated visit.

    Raises:
        VisitLockedError: If the visit is archived.
    """
    if not visit.is_active:
        raise VisitLockedError()
    visit.current_status = VisitInstance.Status.SCHEDULED
    visit.completed_at = None
    visit.updated_by = user
    visit.save(
        update_fields=["current_status", "completed_at", "updated_by", "updated_at"]
    )
    return visit


def get_first_incomplete_section(visit: VisitInstance) -> Optional[str]:
    """Return the id of the first section that still has a required field to answer.

    Args:
        visit: Visit to inspect.

    Returns:
        The section id, or None if every required field is answered.
    """
    for section in compute_progress(visit.instance_schema, visit.answers)["by_section"]:
        if section["missing_required"]:
            return section["id"]
    return None


def coerce_input(field: dict, raw: Optional[str]) -> Any:
    """Convert the raw string posted by the form into the JSON value of the field.

    Args:
        field: Field definition, from the snapshot.
        raw: Posted string. None or an empty string means "no answer".

    Returns:
        None for no answer, a bool for a boolean field, an int or float for a number
        field (a comma is accepted as decimal separator), the string otherwise.

    Raises:
        django.core.exceptions.ValidationError: If the string cannot be read.
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
        # float() also reads "nan" and "inf", which are not valid JSON values
        if not math.isfinite(number):
            raise ValidationError("Un nombre est attendu.")
        return int(number) if number.is_integer() else number
    return raw


def get_form_field(visit: VisitInstance, field_id: str) -> Optional[dict]:
    """Return the definition of a field from the snapshot of the visit.

    Args:
        visit: Visit holding the snapshot.
        field_id: Id of the field.

    Returns:
        The field definition, or None if the snapshot has no such field.
    """
    for _, field in iter_schema_fields(visit.instance_schema):
        if field["id"] == field_id:
            return field
    return None


def build_form_context(
    visit: VisitInstance,
    section_id: Optional[str] = None,
    errors: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Build everything the visit form needs.

    The structure comes from the snapshot of the visit, never from the template.

    Args:
        visit: Visit being filled.
        section_id: Id of the section to show, the first one by default.
        errors: Error message by field id, shown next to the fields.

    Returns:
        The template context: ``progress``, the ``nav`` of sections, the current
        ``section`` and its ``fields`` (with their ``value`` and ``error``), the ids
        of the previous and next sections, and ``readonly`` for a done or archived
        visit.
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
