"""Tests for the template schema validation (inspections/validators.py).

Pure functions: no database is needed, hence ``SimpleTestCase``.
"""

from copy import deepcopy

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from inspections.tests.factories import SAMPLE_SCHEMA
from inspections.validators import (
    get_default_template_structure,
    iter_schema_fields,
    validate_template_schema,
)


def _field(field_id, field_type="text", **extra):
    """Build a field definition.

    Args:
        field_id: Identifier of the field.
        field_type: One of ``boolean``, ``text``, ``select``, ``number``.
        **extra: Other keys of the field (``options``, ``min``...).

    Returns:
        The field as a dict.
    """
    return {"id": field_id, "label": field_id, "type": field_type, "order": 1, **extra}


def _schema(*sections):
    """Build a schema from ``(section id, fields)`` pairs.

    Args:
        *sections: Pairs of a section id and its list of fields.

    Returns:
        The schema as a dict.
    """
    return {
        "version": "1.0",
        "sections": [
            {"id": sid, "title": sid, "order": i, "fields": fields}
            for i, (sid, fields) in enumerate(sections, start=1)
        ],
    }


class ValidateTemplateSchemaTests(SimpleTestCase):
    """``validate_template_schema`` on valid and invalid structures."""

    def test_sample_schema_is_valid(self):
        """The schema used by the test factories is valid and returned unchanged."""
        self.assertEqual(validate_template_schema(SAMPLE_SCHEMA), SAMPLE_SCHEMA)

    def test_default_structure_is_valid(self):
        """The skeleton given to a new template passes the validation."""
        validate_template_schema(get_default_template_structure())

    def test_non_dict_is_refused(self):
        """A schema that is not a JSON object is refused with a readable message."""
        with self.assertRaisesMessage(ValidationError, "un objet est attendu"):
            validate_template_schema(["not", "a", "dict"])

    def test_empty_sections_are_refused(self):
        """A template without any section is refused."""
        with self.assertRaisesMessage(ValidationError, "au moins une section"):
            validate_template_schema({"version": "1.0", "sections": []})

    def test_duplicate_section_ids_are_refused(self):
        """Two sections with the same id are refused."""
        schema = _schema(("a", [_field("f1")]), ("a", [_field("f2")]))
        with self.assertRaisesMessage(ValidationError, "section doivent être uniques"):
            validate_template_schema(schema)

    def test_duplicate_field_ids_in_a_section_are_refused(self):
        """Two fields with the same id in one section are refused."""
        schema = _schema(("a", [_field("f1"), _field("f1")]))
        with self.assertRaisesMessage(ValidationError, "champ doivent être uniques"):
            validate_template_schema(schema)

    def test_duplicate_field_ids_across_sections_are_refused(self):
        """Field ids are unique in the whole template, not only per section."""
        schema = _schema(("a", [_field("f1")]), ("b", [_field("f1")]))
        with self.assertRaisesMessage(ValidationError, "dans tout le template"):
            validate_template_schema(schema)

    def test_select_without_options_is_refused(self):
        """A ``select`` field needs at least one option."""
        for options in (None, []):
            with self.subTest(options=options):
                schema = _schema(("a", [_field("f1", "select", options=options)]))
                with self.assertRaisesMessage(ValidationError, "au moins une option"):
                    validate_template_schema(schema)

    def test_select_with_duplicate_options_is_refused(self):
        """A ``select`` field cannot list the same option twice."""
        schema = _schema(("a", [_field("f1", "select", options=["x", "x"])]))
        with self.assertRaisesMessage(ValidationError, "options en double"):
            validate_template_schema(schema)

    def test_unknown_type_is_refused(self):
        """A field type outside boolean/text/select/number is refused."""
        schema = _schema(("a", [_field("f1", "date")]))
        with self.assertRaises(ValidationError):
            validate_template_schema(schema)

    def test_min_greater_than_max_is_refused(self):
        """A number field whose minimum exceeds its maximum is refused."""
        schema = _schema(("a", [_field("f1", "number", min=10, max=1)]))
        with self.assertRaisesMessage(ValidationError, "minimum supérieur"):
            validate_template_schema(schema)

    def test_number_with_unit_and_step_is_accepted(self):
        """A number field may carry a unit, a step and bounds."""
        schema = _schema(
            ("a", [_field("f1", "number", unit="m", step=0.5, min=0, max=10)])
        )
        validate_template_schema(schema)

    def test_error_message_locates_the_faulty_field(self):
        """The message tells where the problem is, not only that there is one."""
        schema = deepcopy(SAMPLE_SCHEMA)
        del schema["sections"][0]["fields"][0]["label"]
        with self.assertRaises(ValidationError) as ctx:
            validate_template_schema(schema)
        message = " ".join(ctx.exception.messages)
        self.assertIn("sections > 0 > fields > 0 > label", message)
        self.assertTrue(
            message.startswith("Le format JSON de la structure est invalide")
        )


class IterSchemaFieldsTests(SimpleTestCase):
    """``iter_schema_fields`` walks every field in display order."""

    def test_yields_every_field_with_its_section(self):
        """All the fields of all sections are yielded as ``(section, field)``."""
        pairs = list(iter_schema_fields(SAMPLE_SCHEMA))
        self.assertEqual(
            [field["id"] for _, field in pairs],
            ["f_acces_libre", "f_observation", "f_niveau", "f_mesure", "f_remarques"],
        )
        self.assertEqual(pairs[2][0]["id"], "s_mesures")

    def test_follows_the_order_keys(self):
        """Sections and fields are sorted by their ``order``, not by position."""
        schema = _schema(("b", [_field("f2"), _field("f1")]), ("a", [_field("f0")]))
        schema["sections"][0]["order"] = 2
        schema["sections"][1]["order"] = 1
        schema["sections"][0]["fields"][0]["order"] = 2
        ids = [field["id"] for _, field in iter_schema_fields(schema)]
        self.assertEqual(ids, ["f0", "f1", "f2"])

    def test_empty_schema_yields_nothing(self):
        """A schema without sections gives no field."""
        self.assertEqual(list(iter_schema_fields({})), [])
