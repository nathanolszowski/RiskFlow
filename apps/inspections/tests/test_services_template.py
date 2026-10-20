"""Tests for the template services and the server-side editor (inspections/services/template.py).

The editor tests use hand-built ``QueryDict`` objects, like the editor form posts.
"""

from copy import deepcopy

from accounts.tests.factories import UserFactory
from django.core.exceptions import ValidationError
from django.http import Http404, QueryDict
from django.test import SimpleTestCase, TestCase

from inspections.models import VisitTemplate
from inspections.services.template import (
    apply_editor_operation,
    count_fields,
    create_template,
    delete_template,
    duplicate_template,
    get_filtered_templates,
    get_owned_template_by_id,
    get_template_by_id,
    get_usable_templates,
    set_template_shared,
    structure_from_post,
    update_template,
    validate_editor_structure,
)
from inspections.tests.factories import SAMPLE_SCHEMA, VisitTemplateFactory
from inspections.validators import validate_template_schema


class TemplateQueriesTests(TestCase):
    """Getters of templates.

    Data: ``me`` owns an active, a shared and an archived template; ``other`` owns a
    private, a shared and an archived-shared template.
    """

    @classmethod
    def setUpTestData(cls):
        """Create the templates of two users."""
        cls.me = UserFactory()
        cls.other = UserFactory()
        cls.mine = VisitTemplateFactory(created_by=cls.me, name="Mon template")
        cls.mine_shared = VisitTemplateFactory(
            created_by=cls.me, shared=True, name="Mon partagé"
        )
        cls.mine_archived = VisitTemplateFactory(
            created_by=cls.me, archived=True, name="Mon archivé"
        )
        cls.theirs = VisitTemplateFactory(created_by=cls.other, name="Privé autre")
        cls.theirs_shared = VisitTemplateFactory(
            created_by=cls.other, shared=True, name="Partagé autre"
        )
        cls.theirs_shared_archived = VisitTemplateFactory(
            created_by=cls.other, shared=True, archived=True, name="Partagé archivé"
        )

    def test_usable_templates_are_active_and_mine_or_shared(self):
        """Own and shared active templates are usable, nothing else."""
        usable = set(get_usable_templates(self.me))
        self.assertEqual(usable, {self.mine, self.mine_shared, self.theirs_shared})

    def test_filtered_templates_mine(self):
        """The ``mine`` scope lists my templates, archived ones last."""
        templates = list(get_filtered_templates(self.me, "mine"))
        self.assertEqual(
            set(templates), {self.mine, self.mine_shared, self.mine_archived}
        )
        self.assertEqual(templates[-1], self.mine_archived)

    def test_filtered_templates_mine_by_status(self):
        """The status filter splits my active and archived templates."""
        self.assertEqual(
            set(get_filtered_templates(self.me, "mine", status="archived")),
            {self.mine_archived},
        )
        self.assertEqual(
            set(get_filtered_templates(self.me, "mine", status="active")),
            {self.mine, self.mine_shared},
        )

    def test_filtered_templates_shared(self):
        """The ``shared`` scope lists active templates shared by the others only."""
        self.assertEqual(
            list(get_filtered_templates(self.me, "shared")), [self.theirs_shared]
        )

    def test_filtered_templates_search(self):
        """The query searches the name (and description), case-insensitively."""
        found = get_filtered_templates(self.me, "mine", query="  ARCHIVÉ ")
        self.assertEqual(list(found), [self.mine_archived])

    def test_get_template_by_id_rules(self):
        """The owner and readers of an active shared template get it, others a 404."""
        self.assertEqual(get_template_by_id(self.mine.pk, self.me), self.mine)
        self.assertEqual(
            get_template_by_id(self.theirs_shared.pk, self.me), self.theirs_shared
        )
        for template in (self.theirs, self.theirs_shared_archived):
            with self.subTest(template=template.name), self.assertRaises(Http404):
                get_template_by_id(template.pk, self.me)

    def test_get_owned_template_by_id(self):
        """Only the owner gets the template, even when it is shared."""
        self.assertEqual(get_owned_template_by_id(self.mine.pk, self.me), self.mine)
        with self.assertRaises(Http404):
            get_owned_template_by_id(self.theirs_shared.pk, self.me)

    def test_count_fields(self):
        """Fields are counted over all sections, None and empty give 0."""
        self.assertEqual(count_fields(SAMPLE_SCHEMA), 5)
        self.assertEqual(count_fields(None), 0)
        self.assertEqual(count_fields({}), 0)


class TemplateWritesTests(TestCase):
    """Creation, update, duplication, sharing and deletion of templates."""

    def setUp(self):
        """Create a user and one of their templates."""
        self.user = UserFactory()
        self.template = VisitTemplateFactory(created_by=self.user)

    def test_create_template_strips_and_defaults(self):
        """The name is stripped and the schema defaults to the skeleton."""
        template = create_template(self.user, "  Nom  ", description=" desc ")
        self.assertEqual((template.name, template.description), ("Nom", "desc"))
        self.assertFalse(template.shared)
        self.assertEqual(template.created_by, self.user)
        self.assertEqual(template.updated_by, self.user)
        self.assertEqual(count_fields(template.schema), 1)

    def test_create_template_with_invalid_schema_is_refused(self):
        """An invalid schema raises ValidationError and nothing is saved."""
        before = VisitTemplate.objects.count()
        with self.assertRaises(ValidationError):
            create_template(self.user, "X", schema={"sections": []})
        self.assertEqual(VisitTemplate.objects.count(), before)

    def test_update_template(self):
        """The fields are replaced and ``updated_by`` is recorded."""
        other = UserFactory()
        schema = deepcopy(SAMPLE_SCHEMA)
        schema["sections"].pop()
        update_template(self.template, other, " Nouveau ", " d ", True, schema)
        self.template.refresh_from_db()
        self.assertEqual(self.template.name, "Nouveau")
        self.assertTrue(self.template.shared)
        self.assertEqual(len(self.template.schema["sections"]), 1)
        self.assertEqual(self.template.updated_by, other)

    def test_update_template_with_invalid_schema_is_refused(self):
        """An invalid schema is refused and the stored template is unchanged."""
        with self.assertRaises(ValidationError):
            update_template(
                self.template, self.user, "Nom", "", False, {"sections": []}
            )
        self.template.refresh_from_db()
        self.assertEqual(self.template.schema, SAMPLE_SCHEMA)

    def test_duplicate_template(self):
        """A copy belongs to the user, is private and is a deep copy."""
        shared = VisitTemplateFactory(shared=True, description="d")
        copy_ = duplicate_template(shared, self.user)
        self.assertNotEqual(copy_.pk, shared.pk)
        self.assertEqual(copy_.created_by, self.user)
        self.assertFalse(copy_.shared)
        self.assertEqual(copy_.name, f"{shared.name} (copie)")
        self.assertEqual(copy_.description, "d")
        copy_.schema["sections"][0]["title"] = "Modifié"
        copy_.save()
        shared.refresh_from_db()
        self.assertEqual(shared.schema["sections"][0]["title"], "Généralités")

    def test_set_template_shared(self):
        """Sharing toggles the flag from any truthy or falsy value."""
        set_template_shared(self.template, self.user, "on")
        self.assertTrue(VisitTemplate.objects.get(pk=self.template.pk).shared)
        set_template_shared(self.template, self.user, "")
        self.assertFalse(VisitTemplate.objects.get(pk=self.template.pk).shared)

    def test_delete_template_requires_archiving(self):
        """An active template cannot be deleted, an archived one is removed."""
        with self.assertRaises(ValueError):
            delete_template(self.template)
        self.template.archive(self.user)
        delete_template(self.template)
        self.assertFalse(VisitTemplate.objects.filter(pk=self.template.pk).exists())

    def test_save_validates_unless_update_fields(self):
        """``save()`` runs ``full_clean()``, but not with ``update_fields``."""
        self.template.schema = {"sections": []}
        with self.assertRaises(ValidationError):
            self.template.save()
        self.template.description = "partiel"
        self.template.save(update_fields=["description"])
        self.template.refresh_from_db()
        self.assertEqual(self.template.description, "partiel")
        self.assertEqual(self.template.schema, SAMPLE_SCHEMA)


def make_post(*sections):
    """Build the ``QueryDict`` posted by the editor form.

    Args:
        *sections: Tuples ``(id, title, fields)`` where ``fields`` is a list of dicts
            with the keys ``id``, ``label``, ``type`` and optionally ``required``
            (bool), ``options`` (str) and ``unit`` (str).

    Returns:
        The posted data, with the ``s<i>-...`` / ``s<i>-f<j>-...`` names.
    """
    post = QueryDict(mutable=True)
    for i, (sid, title, fields) in enumerate(sections):
        post[f"s{i}-id"] = sid
        post[f"s{i}-title"] = title
        for j, field in enumerate(fields):
            prefix = f"s{i}-f{j}"
            post[f"{prefix}-id"] = field["id"]
            post[f"{prefix}-label"] = field.get("label", "")
            post[f"{prefix}-type"] = field.get("type", "boolean")
            if field.get("required"):
                post[f"{prefix}-required"] = "on"
            if "options" in field:
                post[f"{prefix}-options"] = field["options"]
            if "unit" in field:
                post[f"{prefix}-unit"] = field["unit"]
    return post


def ids(structure):
    """Return the section ids and the field ids of a structure.

    Args:
        structure: Template structure.

    Returns:
        A tuple ``(section ids, [field ids per section])``.
    """
    sections = structure["sections"]
    return [s["id"] for s in sections], [
        [f["id"] for f in s["fields"]] for s in sections
    ]


class StructureFromPostTests(SimpleTestCase):
    """``structure_from_post`` rebuilds the structure from the editor form."""

    def test_rebuilds_sections_fields_and_orders(self):
        """Ids are kept, orders are numbered from the DOM position, text is stripped."""
        post = make_post(
            ("sec_a", " Titre A ", [{"id": "f_1", "label": " Q1 ", "required": True}]),
            ("sec_b", "Titre B", []),
        )
        structure = structure_from_post(post)
        self.assertEqual(structure["version"], "1.0")
        self.assertEqual(ids(structure), (["sec_a", "sec_b"], [["f_1"], []]))
        self.assertEqual(structure["sections"][0]["title"], "Titre A")
        self.assertEqual([s["order"] for s in structure["sections"]], [1, 2])
        field = structure["sections"][0]["fields"][0]
        self.assertEqual(
            (field["label"], field["required"], field["order"]), ("Q1", True, 1)
        )

    def test_checkbox_absent_means_not_required(self):
        """An unchecked box is missing from the POST: the field is optional."""
        structure = structure_from_post(
            make_post(("s", "T", [{"id": "f", "label": "L"}]))
        )
        self.assertFalse(structure["sections"][0]["fields"][0]["required"])

    def test_select_options_and_number_unit(self):
        """Options accept commas and new lines, the unit only applies to numbers."""
        post = make_post(
            (
                "s",
                "T",
                [
                    {"id": "a", "label": "A", "type": "select", "options": "x, y\nz,,"},
                    {"id": "b", "label": "B", "type": "number", "unit": " kg "},
                    {"id": "c", "label": "C", "type": "text", "unit": "kg"},
                ],
            )
        )
        fields = structure_from_post(post)["sections"][0]["fields"]
        self.assertEqual(fields[0]["options"], ["x", "y", "z"])
        self.assertEqual(fields[1]["unit"], "kg")
        self.assertNotIn("unit", fields[2])
        self.assertNotIn("options", fields[2])

    def test_empty_post_gives_no_section(self):
        """A form without section gives an empty list of sections."""
        self.assertEqual(structure_from_post(QueryDict())["sections"], [])


class EditorOperationsTests(SimpleTestCase):
    """``apply_editor_operation`` on a three-sections structure."""

    def setUp(self):
        """Build a structure with sections a, b, c holding fields a1-a2, b1, nothing."""
        self.structure = structure_from_post(
            make_post(
                ("a", "A", [{"id": "a1", "label": "1"}, {"id": "a2", "label": "2"}]),
                ("b", "B", [{"id": "b1", "label": "1"}]),
                ("c", "C", []),
            )
        )

    def test_add_section(self):
        """A section with a generated id and no field is appended."""
        apply_editor_operation(self.structure, "add_section")
        sections = self.structure["sections"]
        self.assertEqual(len(sections), 4)
        self.assertTrue(sections[-1]["id"].startswith("sec_"))
        self.assertEqual(sections[-1]["fields"], [])
        self.assertEqual([s["order"] for s in sections], [1, 2, 3, 4])

    def test_remove_section(self):
        """The section at the index is removed and orders are renumbered."""
        apply_editor_operation(self.structure, "remove_section", section=1)
        self.assertEqual(ids(self.structure)[0], ["a", "c"])
        self.assertEqual([s["order"] for s in self.structure["sections"]], [1, 2])

    def test_move_section_up_and_down(self):
        """Sections swap with their neighbour."""
        apply_editor_operation(self.structure, "move_section_up", section=1)
        self.assertEqual(ids(self.structure)[0], ["b", "a", "c"])
        apply_editor_operation(self.structure, "move_section_down", section=0)
        self.assertEqual(ids(self.structure)[0], ["a", "b", "c"])

    def test_first_section_up_and_last_section_down_do_nothing(self):
        """Moving past the ends leaves the order unchanged."""
        apply_editor_operation(self.structure, "move_section_up", section=0)
        apply_editor_operation(self.structure, "move_section_down", section=2)
        self.assertEqual(ids(self.structure)[0], ["a", "b", "c"])

    def test_add_field(self):
        """An optional boolean field with a generated id is appended."""
        apply_editor_operation(self.structure, "add_field", section=2)
        field = self.structure["sections"][2]["fields"][0]
        self.assertTrue(field["id"].startswith("f_"))
        self.assertEqual(
            (field["type"], field["required"], field["order"]), ("boolean", False, 1)
        )

    def test_remove_field(self):
        """The field at the index is removed and orders are renumbered."""
        apply_editor_operation(self.structure, "remove_field", section=0, field=0)
        self.assertEqual(ids(self.structure)[1][0], ["a2"])
        self.assertEqual(self.structure["sections"][0]["fields"][0]["order"], 1)

    def test_move_field_up_and_down(self):
        """Fields swap with their neighbour inside their section."""
        apply_editor_operation(self.structure, "move_field_down", section=0, field=0)
        self.assertEqual(ids(self.structure)[1][0], ["a2", "a1"])
        apply_editor_operation(self.structure, "move_field_up", section=0, field=1)
        self.assertEqual(ids(self.structure)[1][0], ["a1", "a2"])

    def test_first_field_up_and_last_field_down_do_nothing(self):
        """Moving a field past the ends of its section changes nothing."""
        apply_editor_operation(self.structure, "move_field_up", section=0, field=0)
        apply_editor_operation(self.structure, "move_field_down", section=0, field=1)
        self.assertEqual(ids(self.structure)[1][0], ["a1", "a2"])

    def test_out_of_range_indexes_are_ignored(self):
        """Unknown indexes never raise and never change the structure."""
        before = deepcopy(self.structure)
        operations = [
            ("remove_section", 9, None),
            ("remove_section", -1, None),
            ("move_section_up", 9, None),
            ("add_field", 9, None),
            ("remove_field", 9, 0),
            ("remove_field", 0, 9),
            ("move_field_down", 9, 0),
            ("move_field_up", 0, 9),
            ("remove_field", None, None),
            ("unknown_operation", 0, 0),
        ]
        for op, section, field in operations:
            with self.subTest(op=op, section=section, field=field):
                apply_editor_operation(self.structure, op, section=section, field=field)
                self.assertEqual(self.structure, before)

    def test_generated_ids_stay_stable_across_operations(self):
        """Ids created by an operation survive the next ones (moves, additions)."""
        apply_editor_operation(self.structure, "add_section")
        new_id = self.structure["sections"][-1]["id"]
        apply_editor_operation(self.structure, "add_field", section=3)
        field_id = self.structure["sections"][3]["fields"][0]["id"]
        apply_editor_operation(self.structure, "move_section_up", section=3)
        apply_editor_operation(self.structure, "add_section")
        self.assertEqual(self.structure["sections"][2]["id"], new_id)
        self.assertEqual(self.structure["sections"][2]["fields"][0]["id"], field_id)
        all_ids = ids(self.structure)[0]
        self.assertEqual(len(set(all_ids)), len(all_ids))


class ValidateEditorStructureTests(SimpleTestCase):
    """``validate_editor_structure`` returns messages meant for the user."""

    def valid(self):
        """Return a valid structure built through ``structure_from_post``.

        Returns:
            A one-section, one-field structure.
        """
        return structure_from_post(
            make_post(("s", "Titre", [{"id": "f", "label": "Question"}]))
        )

    def test_valid_structure_is_returned(self):
        """A complete structure passes and is returned unchanged."""
        structure = self.valid()
        self.assertEqual(validate_editor_structure(structure), structure)
        validate_template_schema(structure)

    def test_section_without_title_is_refused(self):
        """Every section needs a title."""
        structure = self.valid()
        structure["sections"][0]["title"] = ""
        with self.assertRaisesMessage(ValidationError, "doit avoir un titre"):
            validate_editor_structure(structure)

    def test_field_without_label_is_refused(self):
        """Every field needs a label, the message names the section."""
        structure = self.valid()
        structure["sections"][0]["fields"][0]["label"] = ""
        with self.assertRaisesMessage(ValidationError, "« Titre »"):
            validate_editor_structure(structure)

    def test_unknown_field_type_is_refused(self):
        """A type outside the four known ones is refused."""
        structure = self.valid()
        structure["sections"][0]["fields"][0]["type"] = "date"
        with self.assertRaisesMessage(ValidationError, "Type de champ inconnu"):
            validate_editor_structure(structure)

    def test_schema_errors_are_raised(self):
        """Schema rules still apply (a select needs options)."""
        structure = structure_from_post(
            make_post(("s", "T", [{"id": "f", "label": "L", "type": "select"}]))
        )
        with self.assertRaisesMessage(ValidationError, "au moins une option"):
            validate_editor_structure(structure)

    def test_no_section_is_refused(self):
        """A structure without any section is refused by the schema."""
        with self.assertRaises(ValidationError):
            validate_editor_structure({"version": "1.0", "sections": []})
