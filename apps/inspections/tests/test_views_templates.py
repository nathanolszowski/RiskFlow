"""Tests for the template views (inspections/views_templates.py): side panel, editor, actions."""

from core.tests.helpers import HtmxClientMixin
from django.test import TestCase
from django.urls import reverse

from inspections.models import VisitTemplate
from inspections.tests.factories import (
    SAMPLE_SCHEMA,
    InspectionFolderFactory,
    VisitInstanceFactory,
    VisitTemplateFactory,
)

DRAWER = "inspections/partials/template/template_drawer.html"
PANEL = "inspections/partials/template/template_panel.html"
LIST = "inspections/partials/template/template_list.html"
EDITOR = "inspections/partials/template/template_editor.html"
STRUCTURE = "inspections/partials/template/template_editor_structure.html"
MODAL = "core/partials/modal/archive_confirm_modal.html"


def editor_post(**overrides):
    """Build the data posted by the editor form (one section with one field).

    Args:
        **overrides: Values replacing the defaults (``name``, ``s0-f0-label``...).

    Returns:
        The data to post.
    """
    data = {
        "name": "Audit entrepôt",
        "description": "Pour les entrepôts",
        "s0-id": "sec_a",
        "s0-title": "Sécurité",
        "s0-f0-id": "f_a",
        "s0-f0-label": "Extincteurs en place ?",
        "s0-f0-type": "boolean",
        "s0-f0-required": "on",
    }
    data.update(overrides)
    return data


class TemplateViewTestCase(HtmxClientMixin, TestCase):
    """Base class: the owner has a private template; another user shares one."""

    def setUp(self):
        """Create the templates."""
        super().setUp()
        self.mine = VisitTemplateFactory(created_by=self.owner, name="Mon template")
        self.shared = VisitTemplateFactory(
            created_by=self.other, shared_template=True, name="Partagé par l'autre"
        )

    def url(self, name, *args):
        """Reverse an ``inspections`` URL.

        Args:
            name: URL name without the namespace.
            *args: URL arguments.

        Returns:
            The URL.
        """
        return reverse(f"inspections:{name}", args=args)


class TemplatePanelTests(TemplateViewTestCase):
    """``template_panel``: drawer, panel and list."""

    def test_opening_loads_the_whole_drawer(self):
        """The ``drawer-container`` target gets the full drawer."""
        response = self.htmx_get(
            self.url("template_panel"), HTTP_HX_TARGET="drawer-container"
        )
        self.assertTemplateUsed(response, DRAWER)
        self.assertContains(response, "Mon template")

    def test_tabs_and_search_reload_the_list_only(self):
        """The ``template-list`` target gets the list, anything else the panel."""
        response = self.htmx_get(
            self.url("template_panel"), HTTP_HX_TARGET="template-list"
        )
        self.assertTemplateUsed(response, LIST)
        self.assertTemplateNotUsed(response, PANEL)
        response = self.htmx_get(
            self.url("template_panel"), HTTP_HX_TARGET="template-drawer-content"
        )
        self.assertTemplateUsed(response, PANEL)

    def test_mine_scope_is_the_default(self):
        """The panel lists my templates by default, not the shared ones of others."""
        response = self.htmx_get(self.url("template_panel"))
        self.assertEqual(response.context["scope"], "mine")
        self.assertEqual([t.pk for t in response.context["templates"]], [self.mine.pk])

    def test_shared_scope(self):
        """The shared scope lists the templates shared by the others, flagged as not mine."""
        response = self.htmx_get(self.url("template_panel"), {"scope": "shared"})
        templates = response.context["templates"]
        self.assertEqual([t.pk for t in templates], [self.shared.pk])
        self.assertFalse(templates[0].is_mine)
        self.assertEqual(templates[0].field_count, 5)
        self.assertEqual(
            (response.context["mine_count"], response.context["shared_count"]), (1, 1)
        )

    def test_unknown_scope_falls_back_to_mine(self):
        """An unknown scope is replaced by ``mine``."""
        response = self.htmx_get(self.url("template_panel"), {"scope": "everyone"})
        self.assertEqual(response.context["scope"], "mine")

    def test_search_and_status_filters(self):
        """The query and the status narrow the list."""
        archived = VisitTemplateFactory(
            created_by=self.owner, archived=True, name="Ancien"
        )
        response = self.htmx_get(self.url("template_panel"), {"status": "archived"})
        self.assertEqual([t.pk for t in response.context["templates"]], [archived.pk])
        response = self.htmx_get(self.url("template_panel"), {"q": "mon"})
        self.assertEqual([t.pk for t in response.context["templates"]], [self.mine.pk])

    def test_folder_parameter_must_belong_to_the_user(self):
        """The panel opened from a folder keeps its id, a foreign folder gives a 404."""
        own = InspectionFolderFactory(created_by=self.owner)
        response = self.htmx_get(self.url("template_panel"), {"folder": own.pk})
        self.assertEqual(response.context["folder_id"], own.pk)
        foreign = InspectionFolderFactory(created_by=self.other)
        self.assertEqual(
            self.htmx_get(
                self.url("template_panel"), {"folder": foreign.pk}
            ).status_code,
            404,
        )


class TemplateEditorTests(TemplateViewTestCase):
    """``template_create``, ``template_edit``, ``template_read``."""

    def test_create_get_gives_an_editor_with_one_empty_section(self):
        """A new template starts with one empty section with a generated id."""
        response = self.htmx_get(self.url("template_create"))
        self.assertTemplateUsed(response, EDITOR)
        sections = response.context["structure"]["sections"]
        self.assertEqual(len(sections), 1)
        self.assertTrue(sections[0]["id"].startswith("sec_"))
        self.assertIsNone(response.context["template"])

    def test_create_post_saves_and_returns_the_list(self):
        """A valid POST creates the template for the user and shows the list."""
        response = self.htmx_post(self.url("template_create"), editor_post(shared="on"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, PANEL)
        template = VisitTemplate.objects.get(name="Audit entrepôt")
        self.assertEqual((template.created_by, template.shared), (self.owner, True))
        self.assertEqual(template.schema["sections"][0]["id"], "sec_a")
        self.assertEqual(template.schema["sections"][0]["fields"][0]["id"], "f_a")
        self.assertTrue(template.schema["sections"][0]["fields"][0]["required"])

    def test_create_post_without_name_is_422(self):
        """A missing name re-renders the editor with the error and keeps the structure."""
        response = self.htmx_post(self.url("template_create"), editor_post(name=" "))
        self.assertEqual(response.status_code, 422)
        self.assertTemplateUsed(response, EDITOR)
        self.assertIn("Le nom du template est obligatoire.", response.context["errors"])
        self.assertEqual(
            response.context["structure"]["sections"][0]["fields"][0]["id"], "f_a"
        )
        self.assertFalse(
            VisitTemplate.objects.filter(name__startswith="Audit").exists()
        )

    def test_create_post_with_incomplete_structure_is_422(self):
        """A field without label, a section without title or a select without options is refused."""
        cases = [
            editor_post(**{"s0-f0-label": ""}),
            editor_post(**{"s0-title": ""}),
            editor_post(**{"s0-f0-type": "select", "s0-f0-options": ""}),
            {"name": "Sans section"},
        ]
        for data in cases:
            with self.subTest(data=data):
                response = self.htmx_post(self.url("template_create"), data)
                self.assertEqual(response.status_code, 422)
                self.assertTrue(response.context["errors"])
        self.assertFalse(
            VisitTemplate.objects.filter(
                name__in=["Audit entrepôt", "Sans section"]
            ).exists()
        )

    def test_edit_get_shows_the_template(self):
        """The editor opens with the name and the structure of the template."""
        response = self.htmx_get(self.url("template_edit", self.mine.pk))
        self.assertEqual(response.context["name"], "Mon template")
        self.assertEqual(response.context["structure"], SAMPLE_SCHEMA)
        self.assertFalse(response.context["readonly"])

    def test_edit_post_updates_the_template(self):
        """A valid POST updates the template and shows the list."""
        response = self.htmx_post(
            self.url("template_edit", self.mine.pk), editor_post(name="Renommé")
        )
        self.assertTemplateUsed(response, PANEL)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "Renommé")
        self.assertEqual(len(self.mine.schema["sections"]), 1)
        self.assertEqual(self.mine.updated_by, self.owner)

    def test_edit_does_not_change_existing_visits(self):
        """Editing the template leaves the snapshot of its visits as it was."""
        visit = VisitInstanceFactory(
            template=self.mine, created_by=self.owner, folder__created_by=self.owner
        )
        self.htmx_post(self.url("template_edit", self.mine.pk), editor_post())
        visit.refresh_from_db()
        self.assertEqual(visit.instance_schema, SAMPLE_SCHEMA)

    def test_edit_invalid_post_is_422_and_keeps_the_template(self):
        """An invalid POST keeps the stored template unchanged."""
        response = self.htmx_post(
            self.url("template_edit", self.mine.pk), editor_post(**{"s0-f0-label": ""})
        )
        self.assertEqual(response.status_code, 422)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.schema, SAMPLE_SCHEMA)

    def test_read_of_a_shared_template_is_read_only(self):
        """A template shared by another user opens read-only."""
        response = self.htmx_get(self.url("template_read", self.shared.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["readonly"])
        self.assertContains(response, 'name="s0-title"')
        self.assertContains(response, "disabled")

    def test_read_of_my_template_is_editable(self):
        """My own template is not read-only."""
        response = self.htmx_get(self.url("template_read", self.mine.pk))
        self.assertFalse(response.context["readonly"])

    def test_read_of_an_archived_shared_template_is_404(self):
        """An archived template is no longer readable by the others."""
        self.shared.archive(self.other)
        self.assertEqual(
            self.htmx_get(self.url("template_read", self.shared.pk)).status_code, 404
        )


class EditorOperationTests(TemplateViewTestCase):
    """``template_editor_operation``: the form is the state, nothing is saved."""

    def operate(self, **data):
        """Post an operation with the one-section form.

        Args:
            **data: ``op``, ``section``, ``field`` and other posted values.

        Returns:
            The response.
        """
        return self.htmx_post(
            self.url("template_editor_operation"), {**editor_post(), **data}
        )

    def test_add_section_renders_the_structure_with_the_new_section(self):
        """The fragment holds the existing section and the new one, with a generated id."""
        response = self.operate(op="add_section")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, STRUCTURE)
        self.assertEqual(response.context["section_count"], 2)
        self.assertContains(response, 'value="sec_a"')
        self.assertContains(response, 'name="s1-id"')
        self.assertTrue(response.context["oob"])

    def test_add_field_and_remove_field(self):
        """Fields are added to and removed from the posted form."""
        response = self.operate(op="add_field", section="0")
        self.assertEqual(response.context["field_count"], 2)
        response = self.operate(op="remove_field", section="0", field="0")
        self.assertEqual(response.context["field_count"], 0)
        self.assertEqual(response.context["section_count"], 1)

    def test_posted_values_are_kept(self):
        """What the user typed survives an operation."""
        response = self.operate(op="add_section", **{"s0-title": "Titre tapé"})
        self.assertContains(response, "Titre tapé")

    def test_move_section(self):
        """Sections change place."""
        post = editor_post(**{"s1-id": "sec_b", "s1-title": "Autre"})
        response = self.htmx_post(
            self.url("template_editor_operation"),
            {**post, "op": "move_section_down", "section": "0"},
        )
        self.assertEqual(
            [s["id"] for s in response.context["structure"]["sections"]],
            ["sec_b", "sec_a"],
        )

    def test_unknown_operation_and_bad_index_change_nothing(self):
        """Unknown operations and non-numeric indexes are ignored."""
        for data in (
            {"op": "explode"},
            {"op": "remove_section", "section": "x"},
            {"op": ""},
        ):
            with self.subTest(data=data):
                response = self.operate(**data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["section_count"], 1)

    def test_nothing_is_saved(self):
        """The operation never writes to the database."""
        before = VisitTemplate.objects.count()
        self.operate(op="add_section", template_pk=str(self.mine.pk))
        self.assertEqual(VisitTemplate.objects.count(), before)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.schema, SAMPLE_SCHEMA)

    def test_template_pk_of_someone_else_is_404(self):
        """The template given in the form must belong to the user."""
        response = self.operate(op="add_section", template_pk=str(self.shared.pk))
        self.assertEqual(response.status_code, 404)

    def test_get_is_refused(self):
        """The operation view only accepts POST."""
        self.assertEqual(
            self.client.get(self.url("template_editor_operation")).status_code, 405
        )


class TemplateActionTests(TemplateViewTestCase):
    """Duplicate, share, archive and delete."""

    def test_duplicate_a_shared_template(self):
        """Copying a shared template gives me a private copy and shows my list."""
        response = self.htmx_post(self.url("template_duplicate", self.shared.pk))
        self.assertTemplateUsed(response, PANEL)
        copy_ = VisitTemplate.objects.get(
            created_by=self.owner, name=f"{self.shared.name} (copie)"
        )
        self.assertFalse(copy_.shared)
        self.assertEqual(copy_.schema, self.shared.schema)

    def test_duplicate_my_own_template(self):
        """My own template can be copied too."""
        self.htmx_post(self.url("template_duplicate", self.mine.pk))
        self.assertEqual(VisitTemplate.objects.filter(created_by=self.owner).count(), 2)

    def test_toggle_share_flips_the_flag(self):
        """Each call shares or unshares my template."""
        self.htmx_post(self.url("template_toggle_share", self.mine.pk))
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.shared)
        self.htmx_post(self.url("template_toggle_share", self.mine.pk))
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.shared)

    def test_archive_get_renders_the_modal(self):
        """The modal explains the effect and posts back to the drawer."""
        response = self.htmx_get(self.url("template_archive", self.mine.pk))
        self.assertTemplateUsed(response, MODAL)
        self.assertEqual(response.context["post_target"], "#template-drawer-content")
        self.assertNotIn("items", response.context)

    def test_archive_get_keeps_the_folder_in_the_post_url(self):
        """The folder the panel was opened from is kept in the confirmation URL."""
        response = self.htmx_get(
            self.url("template_archive", self.mine.pk), {"folder": "12"}
        )
        self.assertTrue(response.context["post_url"].endswith("?folder=12"))

    def test_archive_and_unarchive(self):
        """Archiving hides the template from new visits, unarchiving restores it."""
        response = self.htmx_post(self.url("template_archive", self.mine.pk))
        self.assertTemplateUsed(response, PANEL)
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.is_active)
        self.htmx_post(self.url("template_unarchive", self.mine.pk))
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_active)

    def test_delete_of_an_active_template_is_blocked(self):
        """The modal blocks and the POST answers 409."""
        response = self.htmx_get(self.url("template_delete", self.mine.pk))
        self.assertTrue(response.context["blocking"])
        self.assertNotContains(response, "hx-post=")
        self.assertEqual(
            self.htmx_post(self.url("template_delete", self.mine.pk)).status_code, 409
        )
        self.assertTrue(VisitTemplate.objects.filter(pk=self.mine.pk).exists())

    def test_delete_of_an_archived_template(self):
        """An archived template is deleted, and its visits keep their snapshot."""
        visit = VisitInstanceFactory(
            template=self.mine, created_by=self.owner, folder__created_by=self.owner
        )
        self.mine.archive(self.owner)
        response = self.htmx_get(self.url("template_delete", self.mine.pk))
        self.assertFalse(response.context["blocking"])
        self.assertIn("1 visite créée", response.context["sections"][0]["note"])
        response = self.htmx_post(self.url("template_delete", self.mine.pk))
        self.assertTemplateUsed(response, PANEL)
        self.assertFalse(VisitTemplate.objects.filter(pk=self.mine.pk).exists())
        visit.refresh_from_db()
        self.assertIsNone(visit.template)
        self.assertEqual(visit.instance_schema, SAMPLE_SCHEMA)

    def test_actions_on_a_shared_template_of_another_user_are_404(self):
        """Sharing, archiving and deleting need to own the template."""
        for name in (
            "template_toggle_share",
            "template_archive",
            "template_unarchive",
            "template_delete",
        ):
            with self.subTest(url=name):
                self.assertEqual(
                    self.htmx_post(self.url(name, self.shared.pk)).status_code, 404
                )
        self.shared.refresh_from_db()
        self.assertTrue(self.shared.is_active)
