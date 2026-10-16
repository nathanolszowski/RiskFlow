import copy
import uuid

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404

from core.services import delete_archived_instance
from inspections.models import VisitTemplate
from inspections.validators import (
    get_default_template_structure,
    validate_template_schema,
)

TEMPLATE_SCOPES = ("mine", "shared")
FIELD_TYPES = ("boolean", "number", "select", "text")


# ==== QUERIES ====


def get_filtered_templates(user, scope="mine", query="", status="all"):
    """
    Templates listed in the side panel.
    - mine   : templates created by the user, archived ones included (they are listed last).
    - shared : active templates shared by the other users.
    """
    if scope == "shared":
        templates = VisitTemplate.objects.filter(shared=True, is_active=True).exclude(
            created_by=user
        )
    else:
        templates = VisitTemplate.objects.filter(created_by=user)
        if status == "archived":
            templates = templates.filter(is_active=False)
        elif status == "active":
            templates = templates.filter(is_active=True)

    query = (query or "").strip()
    if query:
        templates = templates.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    return templates.select_related("created_by", "updated_by").order_by(
        "-is_active", "-updated_at"
    )


def get_usable_templates(user):
    """Active templates the user can start a visit from: his own and the shared ones."""
    return (
        VisitTemplate.objects.filter(is_active=True)
        .filter(Q(created_by=user) | Q(shared=True))
        .select_related("created_by")
        .order_by("name")
    )


def get_template_by_id(pk, user):
    """A template can be read by its owner, and by everybody when it is shared and active."""
    template = get_object_or_404(
        VisitTemplate.objects.select_related("created_by", "updated_by"), pk=pk
    )
    if template.created_by_id != user.pk and not (
        template.shared and template.is_active
    ):
        raise Http404
    return template


def get_owned_template_by_id(pk, user):
    """Only the owner can change a template."""
    return get_object_or_404(
        VisitTemplate.objects.select_related("created_by", "updated_by"),
        pk=pk,
        created_by=user,
    )


def count_fields(schema):
    return sum(
        len(section.get("fields", [])) for section in (schema or {}).get("sections", [])
    )


# ==== WRITES ====


def create_template(user, name, description="", shared=False, schema=None):
    template = VisitTemplate(
        name=name.strip(),
        description=description.strip(),
        shared=shared,
        schema=schema if schema is not None else get_default_template_structure(),
        created_by=user,
        updated_by=user,
    )
    template.save()
    return template


def update_template(template, user, name, description, shared, schema):
    """Update a template. Visits already created keep their own snapshot and are not affected."""
    template.name = name.strip()
    template.description = description.strip()
    template.shared = shared
    template.schema = schema
    template.updated_by = user
    template.save()
    return template


def duplicate_template(template, user):
    """
    Copy a template (own or shared) into the templates of the user. The copy is private,
    and its ids are kept: they only need to be unique inside one template.
    """
    return create_template(
        user,
        name=f"{template.name} (copie)",
        description=template.description,
        shared=False,
        schema=copy.deepcopy(template.schema),
    )


def set_template_shared(template, user, value):
    template.shared = bool(value)
    template.updated_by = user
    template.save()
    return template


def delete_template(template):
    """Permanent deletion of an archived template. Visits are not blocked: they keep their snapshot."""
    delete_archived_instance(template)


# ==== EDITOR ====
# The editor form is the state: each action posts the whole form, the structure is rebuilt from it,
# one operation is applied, and the editor is rendered again.


def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def new_section(title="Nouvelle section"):
    return {"id": _new_id("sec"), "title": title, "order": 0, "fields": []}


def new_field():
    return {
        "id": _new_id("f"),
        "label": "",
        "type": "boolean",
        "required": False,
        "order": 0,
    }


def structure_from_post(post):
    """
    Rebuild the template structure from the editor form fields:
      s<i>-id, s<i>-title, s<i>-f<j>-id|label|type|required|options|unit
    Indexes follow the DOM order. Ids come from hidden inputs so that they never change.
    """
    sections = []
    i = 0
    while f"s{i}-id" in post:
        fields = []
        j = 0
        while f"s{i}-f{j}-id" in post:
            prefix = f"s{i}-f{j}"
            field_type = post.get(f"{prefix}-type", "boolean")
            field = {
                "id": post.get(f"{prefix}-id"),
                "label": post.get(f"{prefix}-label", "").strip(),
                "type": field_type,
                "required": post.get(f"{prefix}-required") == "on",
                "order": j + 1,
            }
            if field_type == "select":
                raw = post.get(f"{prefix}-options", "")
                field["options"] = [
                    o.strip() for o in raw.replace("\n", ",").split(",") if o.strip()
                ]
            if field_type == "number" and post.get(f"{prefix}-unit", "").strip():
                field["unit"] = post.get(f"{prefix}-unit").strip()
            fields.append(field)
            j += 1
        sections.append(
            {
                "id": post.get(f"s{i}-id"),
                "title": post.get(f"s{i}-title", "").strip(),
                "order": i + 1,
                "fields": fields,
            }
        )
        i += 1
    return {"version": "1.0", "sections": sections}


def apply_editor_operation(structure, op, section=None, field=None):
    """
    Apply one editor action on the structure (modified in place and returned).
    Operations: add_section, remove_section, move_section_up|down, add_field, remove_field, move_field_up|down.
    section and field are indexes.
    """
    sections = structure["sections"]

    if op == "add_section":
        sections.append(new_section())
    elif (
        op == "remove_section" and section is not None and 0 <= section < len(sections)
    ):
        sections.pop(section)
    elif op in ("move_section_up", "move_section_down") and section is not None:
        _move(sections, section, -1 if op.endswith("up") else 1)
    elif op == "add_field" and section is not None and 0 <= section < len(sections):
        sections[section]["fields"].append(new_field())
    elif (
        op in ("remove_field", "move_field_up", "move_field_down")
        and section is not None
        and field is not None
    ):
        if 0 <= section < len(sections):
            fields = sections[section]["fields"]
            if op == "remove_field" and 0 <= field < len(fields):
                fields.pop(field)
            elif op != "remove_field":
                _move(fields, field, -1 if op.endswith("up") else 1)

    for i, sec in enumerate(sections):
        sec["order"] = i + 1
        for j, fld in enumerate(sec["fields"]):
            fld["order"] = j + 1
    return structure


def _move(items, index, delta):
    target = index + delta
    if 0 <= index < len(items) and 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]


def validate_editor_structure(structure):
    """Validate the rebuilt structure. Raise ValidationError with a message for the user."""
    for section in structure["sections"]:
        if not section["title"]:
            raise ValidationError("Chaque section doit avoir un titre.")
        for field in section["fields"]:
            if not field["label"]:
                raise ValidationError(
                    f"Chaque champ de la section « {section['title']} » doit avoir un libellé."
                )
            if field["type"] not in FIELD_TYPES:
                raise ValidationError("Type de champ inconnu.")
    return validate_template_schema(structure)
