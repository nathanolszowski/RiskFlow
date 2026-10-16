from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from inspections.services.inspectionfolder import get_inspection_folder_by_id
from inspections.services.template import (
    TEMPLATE_SCOPES,
    apply_editor_operation,
    count_fields,
    create_template,
    delete_template,
    duplicate_template,
    get_filtered_templates,
    get_owned_template_by_id,
    get_template_by_id,
    new_section,
    set_template_shared,
    structure_from_post,
    update_template,
    validate_editor_structure,
)


# ==========================================
# ==== VISIT TEMPLATES (SIDE PANEL) ========
# ==========================================

def _folder_id(request):
    """Folder the panel was opened from: the "Utiliser" action prepares a visit on it."""
    raw = request.GET.get("folder") or request.POST.get("folder")
    if raw and raw.isdigit():
        # Ownership check: the folder must belong to the user
        return get_inspection_folder_by_id(int(raw), request.user).pk
    return None


def _panel_context(request, scope=None):
    scope = scope or request.GET.get("scope") or request.POST.get("scope") or "mine"
    if scope not in TEMPLATE_SCOPES:
        scope = "mine"
    status = request.GET.get("status") if request.GET.get("status") in ("active", "archived") else "all"
    query = request.GET.get("q", "").strip()
    templates = list(get_filtered_templates(request.user, scope, query, status))
    for template in templates:
        template.field_count = count_fields(template.schema)
        template.is_mine = template.created_by_id == request.user.pk
    return {
        "scope": scope,
        "status": status,
        "q": query,
        "folder_id": _folder_id(request),
        "templates": templates,
        "mine_count": get_filtered_templates(request.user, "mine").count(),
        "shared_count": get_filtered_templates(request.user, "shared").count(),
    }


def _render_panel(request, scope=None, drawer=False):
    """The list of templates. drawer=True renders the whole side panel (overlay included)."""
    context = _panel_context(request, scope)
    if drawer:
        return render(request, "inspections/partials/template_drawer.html", context)
    if request.headers.get("HX-Target") == "template-list":
        return render(request, "inspections/partials/template_list.html", context)
    return render(request, "inspections/partials/template_panel.html", context)


@login_required
@require_GET
def template_panel(request):
    """Side panel: GET opens it (full drawer), then tabs and search reload the list only."""
    if request.headers.get("HX-Target") == "drawer-container":
        return _render_panel(request, drawer=True)
    return _render_panel(request)


# ==========================================
# ==== TEMPLATE EDITOR =====================
# ==========================================

def _editor_context(request, template, structure, *, name, description, shared, readonly=False, errors=None):
    return {
        "template": template,
        "structure": structure,
        "name": name,
        "description": description,
        "shared": shared,
        "readonly": readonly,
        "errors": errors or [],
        "folder_id": _folder_id(request),
        "field_count": sum(len(s["fields"]) for s in structure["sections"]),
        "section_count": len(structure["sections"]),
        "field_types": [("boolean", "Oui / Non"), ("number", "Nombre"), ("select", "Choix"), ("text", "Texte")],
    }


def _render_editor(request, context, status=200):
    return render(request, "inspections/partials/template_editor.html", context, status=status)


def _editor_from_post(request, template):
    """State of the editor posted by the form (the form is the state)."""
    structure = structure_from_post(request.POST)
    return _editor_context(
        request,
        template,
        structure,
        name=request.POST.get("name", ""),
        description=request.POST.get("description", ""),
        shared=request.POST.get("shared") == "on",
    )


def _save_editor(request, template):
    """Validate the posted editor and save it. Return (template, None) or (None, error response)."""
    context = _editor_from_post(request, template)
    errors = []
    if not context["name"].strip():
        errors.append("Le nom du template est obligatoire.")
    try:
        schema = validate_editor_structure(context["structure"])
    except ValidationError as e:
        errors.extend(e.messages)
    if errors:
        context["errors"] = errors
        return None, _render_editor(request, context, status=422)

    try:
        if template is None:
            template = create_template(
                request.user, context["name"], context["description"], context["shared"], schema
            )
        else:
            template = update_template(
                template, request.user, context["name"], context["description"], context["shared"], schema
            )
    except ValidationError as e:
        context["errors"] = e.messages
        return None, _render_editor(request, context, status=422)
    return template, None


@login_required
@require_http_methods(["GET", "POST"])
def template_create(request):
    """
    Create a template.
    - GET  : Render the editor with one empty section.
    - POST : Validate and create. If True -> Render the list of the templates, otherwise the editor (422).
    """
    if request.method == "POST":
        template, error = _save_editor(request, None)
        if error:
            return error
        return _render_panel(request, "mine")

    structure = {"version": "1.0", "sections": [new_section()]}
    return _render_editor(request, _editor_context(request, None, structure, name="", description="", shared=False))


@login_required
@require_http_methods(["GET", "POST"])
def template_edit(request, pk):
    """
    Edit one of the templates of the user. Visits already created keep their own copy of the structure.
    """
    template = get_owned_template_by_id(pk, request.user)

    if request.method == "POST":
        _, error = _save_editor(request, template)
        if error:
            return error
        return _render_panel(request, "mine")

    context = _editor_context(
        request, template, template.schema,
        name=template.name, description=template.description, shared=template.shared,
    )
    return _render_editor(request, context)


@login_required
@require_GET
def template_read(request, pk):
    """Read only view of a template (the ones shared by the other users)."""
    template = get_template_by_id(pk, request.user)
    context = _editor_context(
        request, template, template.schema,
        name=template.name, description=template.description, shared=template.shared,
        readonly=template.created_by_id != request.user.pk,
    )
    return _render_editor(request, context)


@login_required
@require_POST
def template_editor_operation(request):
    """
    Apply one editor action (add / remove / move a section or a field) on the posted form,
    then render the editor again. Nothing is saved.
    """
    pk = request.POST.get("template_pk")
    template = get_owned_template_by_id(int(pk), request.user) if pk and pk.isdigit() else None

    context = _editor_from_post(request, template)

    def index(name):
        value = request.POST.get(name, "")
        return int(value) if value.isdigit() else None

    apply_editor_operation(
        context["structure"], request.POST.get("op", ""), section=index("section"), field=index("field"),
    )
    context["field_count"] = sum(len(s["fields"]) for s in context["structure"]["sections"])
    context["section_count"] = len(context["structure"]["sections"])
    context["oob"] = True
    return render(request, "inspections/partials/template_editor_structure.html", context)


# ==========================================
# ==== TEMPLATE ACTIONS ====================
# ==========================================

@login_required
@require_POST
def template_duplicate(request, pk):
    """Copy a template (own or shared) into the templates of the user."""
    duplicate_template(get_template_by_id(pk, request.user), request.user)
    return _render_panel(request, "mine")


@login_required
@require_POST
def template_toggle_share(request, pk):
    template = get_owned_template_by_id(pk, request.user)
    set_template_shared(template, request.user, not template.shared)
    return _render_panel(request, "mine")


def _template_modal(request, template, **extra):
    return render(request, "core/partials/archive_confirm_modal.html", {
        "object_label": template.name,
        "post_target": "#template-drawer-content",
        **extra,
    })


@login_required
@require_http_methods(["GET", "POST"])
def template_archive(request, pk):
    """
    Archive a template: it is not offered for new visits any more. Existing visits are not affected.
    - GET  : Render the confirmation modal.
    - POST : Archive the template.
    """
    template = get_owned_template_by_id(pk, request.user)

    if request.method == "GET":
        return _template_modal(
            request, template,
            title="Archiver ce template ?",
            post_url=reverse("inspections:template_archive", args=[template.pk]) + _folder_query(request),
            sections=[{
                "warning": True,
                "title": "Ce template ne sera plus proposé pour préparer une visite.",
                "note": "Les visites déjà créées gardent leur formulaire. Si le template est partagé, les autres inspecteurs ne le voient plus.",
            }],
        )

    template.archive(user=request.user)
    return _render_panel(request, "mine")


@login_required
@require_POST
def template_unarchive(request, pk):
    template = get_owned_template_by_id(pk, request.user)
    template.unarchive(user=request.user)
    return _render_panel(request, "mine")


@login_required
@require_http_methods(["GET", "POST"])
def template_delete(request, pk):
    """
    Permanently delete an archived template. Visits made from it are not blocked: they keep their own copy.
    - GET  : Render the confirmation modal.
    - POST : Delete the template (409 if it is still active).
    """
    template = get_owned_template_by_id(pk, request.user)

    if request.method == "GET":
        used = template.instances.count()
        blocking = None
        if template.is_active:
            blocking = {
                "title": "Suppression impossible : ce template n'est pas archivé.",
                "note": "Archivez-le d'abord, puis supprimez-le.",
            }
        return render(request, "core/partials/archive_confirm_modal.html", {
            "title": "Supprimer définitivement ce template ?",
            "object_label": template.name,
            "action_verb": "supprimer définitivement",
            "confirm_label": "Supprimer définitivement",
            "danger": True,
            "post_url": reverse("inspections:template_delete", args=[template.pk]) + _folder_query(request),
            "post_target": "#template-drawer-content",
            "blocking": blocking,
            "sections": [{
                "warning": True,
                "title": "Cette action est irréversible.",
                "note": (
                    f"{used} visite{'s' if used > 1 else ''} créée{'s' if used > 1 else ''} depuis ce template "
                    f"garde{'nt' if used > 1 else ''} son formulaire et le nom du template."
                ),
            }],
        })

    if template.is_active:
        return HttpResponse("Le template doit être archivé avant d'être supprimé.", status=409)

    delete_template(template)
    return _render_panel(request, "mine")


def _folder_query(request):
    folder_id = request.GET.get("folder")
    return f"?folder={folder_id}" if folder_id and folder_id.isdigit() else ""
