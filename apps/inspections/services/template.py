"""Services of the visit templates: queries, writes and the server-side editor.

Only the owner changes, archives or deletes a template. A shared template can be
read and copied by other users.
"""

import copy
import uuid
from typing import TYPE_CHECKING, Any, Optional

from core.services import delete_archived_instance
from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.http import Http404, QueryDict
from django.shortcuts import get_object_or_404

from inspections.models import VisitTemplate
from inspections.validators import (
    get_default_template_structure,
    validate_template_schema,
)

if TYPE_CHECKING:
    from accounts.models import CustomUser

TEMPLATE_SCOPES = ("mine", "shared")
FIELD_TYPES = ("boolean", "number", "select", "text")


# ==== QUERIES ====


def get_filtered_templates(
    user: "CustomUser", scope: str = "mine", query: str = "", status: str = "all"
) -> QuerySet:
    """Return the templates listed in the side panel.

    Args:
        user: Logged-in user.
        scope: ``"mine"`` for the templates created by the user, archived ones
            included (listed last), or ``"shared"`` for the active templates shared
            by the other users.
        query: Text searched in the name and the description.
        status: ``"active"``, ``"archived"`` or ``"all"`` (``"mine"`` scope only).

    Returns:
        The templates, active ones first, then most recently updated.
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


def get_usable_templates(user: "CustomUser") -> QuerySet:
    """Return the active templates the user can start a visit from: own and shared ones.

    Args:
        user: Logged-in user.

    Returns:
        The templates, ordered by name.
    """
    return (
        VisitTemplate.objects.filter(is_active=True)
        .filter(Q(created_by=user) | Q(shared=True))
        .select_related("created_by")
        .order_by("name")
    )


def get_template_by_id(pk: int, user: "CustomUser") -> VisitTemplate:
    """Return a template that the user is allowed to read.

    A template can be read by its owner, and by everybody when it is shared and active.

    Args:
        pk: Primary key of the template.
        user: Logged-in user.

    Returns:
        The template.

    Raises:
        Http404: If the template does not exist or the user cannot read it.
    """
    template = get_object_or_404(
        VisitTemplate.objects.select_related("created_by", "updated_by"), pk=pk
    )
    if template.created_by_id != user.pk and not (
        template.shared and template.is_active
    ):
        raise Http404
    return template


def get_owned_template_by_id(pk: int, user: "CustomUser") -> VisitTemplate:
    """Return a template owned by the user. Only the owner can change a template.

    Args:
        pk: Primary key of the template.
        user: Logged-in user, who must own the template.

    Returns:
        The template.

    Raises:
        Http404: If the template does not exist or belongs to another user.
    """
    return get_object_or_404(
        VisitTemplate.objects.select_related("created_by", "updated_by"),
        pk=pk,
        created_by=user,
    )


def count_fields(schema: Optional[dict]) -> int:
    """Count the fields of all the sections of a template structure.

    Args:
        schema: Template structure, may be None or empty.

    Returns:
        The number of fields.
    """
    return sum(
        len(section.get("fields", [])) for section in (schema or {}).get("sections", [])
    )


# ==== WRITES ====


def create_template(
    user: "CustomUser",
    name: str,
    description: str = "",
    shared: bool = False,
    schema: Optional[dict] = None,
) -> VisitTemplate:
    """Create a template, validated by ``VisitTemplate.save()``.

    Args:
        user: Owner of the template.
        name: Name, stripped.
        description: Description, stripped.
        shared: Whether other users can use the template.
        schema: Structure of the template, the default skeleton if None.

    Returns:
        The saved template.

    Raises:
        django.core.exceptions.ValidationError: If the structure is invalid.
    """
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


def update_template(
    template: VisitTemplate,
    user: "CustomUser",
    name: str,
    description: str,
    shared: bool,
    schema: dict,
) -> VisitTemplate:
    """Update a template. Visits already created keep their own snapshot and are not affected.

    Args:
        template: Template to update.
        user: User performing the update.
        name: New name, stripped.
        description: New description, stripped.
        shared: Whether other users can use the template.
        schema: New structure of the template.

    Returns:
        The saved template.

    Raises:
        django.core.exceptions.ValidationError: If the structure is invalid.
    """
    template.name = name.strip()
    template.description = description.strip()
    template.shared = shared
    template.schema = schema
    template.updated_by = user
    template.save()
    return template


def duplicate_template(template: VisitTemplate, user: "CustomUser") -> VisitTemplate:
    """Copy a template (own or shared) into the templates of the user.

    The copy is private, and its ids are kept: they only need to be unique inside
    one template.

    Args:
        template: Template to copy.
        user: Owner of the copy.

    Returns:
        The new template, named ``"<name> (copie)"``.
    """
    return create_template(
        user,
        name=f"{template.name} (copie)",
        description=template.description,
        shared=False,
        schema=copy.deepcopy(template.schema),
    )


def set_template_shared(
    template: VisitTemplate, user: "CustomUser", value: Any
) -> VisitTemplate:
    """Share or unshare a template.

    Args:
        template: Template to update.
        user: User performing the action.
        value: Truthy to share the template with all users.

    Returns:
        The saved template.
    """
    template.shared = bool(value)
    template.updated_by = user
    template.save()
    return template


def delete_template(template: VisitTemplate) -> None:
    """Delete permanently an archived template.

    Visits are not blocked: they keep their snapshot.

    Args:
        template: Archived template to delete.

    Raises:
        ValueError: If the template is still active.
    """
    delete_archived_instance(template)


# ==== EDITOR ====
# The editor form is the state: each action posts the whole form, the structure is rebuilt from it,
# one operation is applied, and the editor is rendered again.


def _new_id(prefix: str) -> str:
    """Return a generated id such as ``sec_1a2b3c4d``.

    Args:
        prefix: Prefix of the id (``sec`` for a section, ``f`` for a field).
    """
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def new_section(title: str = "Nouvelle section") -> dict[str, Any]:
    """Return an empty section with a generated id.

    Args:
        title: Title of the section.
    """
    return {"id": _new_id("sec"), "title": title, "order": 0, "fields": []}


def new_field() -> dict[str, Any]:
    """Return a new optional boolean field, without label, with a generated id."""
    return {
        "id": _new_id("f"),
        "label": "",
        "type": "boolean",
        "required": False,
        "order": 0,
    }


def structure_from_post(post: QueryDict) -> dict[str, Any]:
    """Rebuild the template structure from the editor form.

    The form fields are named ``s<i>-id``, ``s<i>-title`` and
    ``s<i>-f<j>-id|label|type|required|options|unit``. Indexes follow the DOM
    order. Ids come from hidden inputs so that they never change.

    Args:
        post: Posted data of the editor form.

    Returns:
        The structure, not yet validated.
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


def apply_editor_operation(
    structure: dict[str, Any],
    op: str,
    section: Optional[int] = None,
    field: Optional[int] = None,
) -> dict[str, Any]:
    """Apply one editor action on the structure.

    The operations are ``add_section``, ``remove_section``, ``move_section_up``,
    ``move_section_down``, ``add_field``, ``remove_field``, ``move_field_up`` and
    ``move_field_down``. Out-of-range indexes are ignored, and the ``order`` values
    are renumbered afterwards.

    Args:
        structure: Structure to change, modified in place.
        op: Operation to apply.
        section: Index of the section concerned.
        field: Index of the field concerned.

    Returns:
        The same structure.
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


def _move(items: list, index: int, delta: int) -> None:
    """Swap an item with its neighbour, in place, unless it would leave the list.

    Args:
        items: List to change.
        index: Index of the item to move.
        delta: Offset of the target position (-1 for up, 1 for down).
    """
    target = index + delta
    if 0 <= index < len(items) and 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]


def validate_editor_structure(structure: dict[str, Any]) -> dict:
    """Validate the structure rebuilt from the editor.

    Args:
        structure: Structure to validate.

    Returns:
        The structure, unchanged.

    Raises:
        django.core.exceptions.ValidationError: With a message for the user, if a
            section has no title, a field has no label or an unknown type, or the
            schema is invalid.
    """
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
