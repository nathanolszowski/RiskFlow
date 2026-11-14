"""Blank PDF export of a visit questionnaire, to fill in by hand on the field."""

from typing import Any

from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from inspections.models import VisitInstance
from inspections.validators import iter_schema_fields


def build_blank_questionnaire_context(visit: VisitInstance) -> dict[str, Any]:
    """Build the template context of the blank questionnaire.

    Only the visit snapshot (``instance_schema``) is read, never the template,
    and the existing answers are deliberately left out.

    Args:
        visit: Visit to export.

    Returns:
        A dict with ``visit``, ``inspector``, ``sections`` (list of
        ``{id, title, fields}``) and ``exported_at``.
    """
    sections: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for section, field in iter_schema_fields(visit.instance_schema or {}):
        entry = by_id.get(section["id"])
        if entry is None:
            entry = {"id": section["id"], "title": section["title"], "fields": []}
            by_id[section["id"]] = entry
            sections.append(entry)
        entry["fields"].append(field)

    # Sections without any field still appear (notes area).
    for section in sorted(
        (visit.instance_schema or {}).get("sections", []),
        key=lambda s: s.get("order", 0),
    ):
        if section["id"] not in by_id:
            sections.append(
                {"id": section["id"], "title": section["title"], "fields": []}
            )

    user = visit.created_by
    profile = getattr(user, "inspector_profile", None)
    inspector = {
        "name": user.get_full_name() or user.get_username(),
        "registration_number": getattr(profile, "registration_number", ""),
    }
    return {
        "visit": visit,
        "inspector": inspector,
        "sections": sections,
        "exported_at": timezone.localtime(),
    }


def render_blank_questionnaire_pdf(visit: VisitInstance) -> bytes:
    """Render the blank questionnaire of a visit as a PDF.

    Args:
        visit: Visit to export.

    Returns:
        The PDF file content.
    """
    html = render_to_string(
        "inspections/pdf/visit_blank.html", build_blank_questionnaire_context(visit)
    )
    return HTML(string=html, base_url=None).write_pdf()
