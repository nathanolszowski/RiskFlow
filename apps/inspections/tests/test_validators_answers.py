"""Tests for the answers validation and the progress (inspections/validators.py).

Pure functions: no database is needed, hence ``SimpleTestCase``.
"""

from copy import deepcopy

from django.test import SimpleTestCase

from inspections.tests.factories import SAMPLE_SCHEMA
from inspections.validators import (
    TEXT_MAX_LENGTH,
    AnswersValidationError,
    compute_progress,
    validate_answers,
)

FULL_ANSWERS = {
    "f_acces_libre": True,
    "f_observation": "RAS",
    "f_niveau": "moyen",
    "f_mesure": 20,
}


class ValidateAnswersTests(SimpleTestCase):
    """``validate_answers`` in the default (non strict) mode."""

    def errors(self, answers, schema=SAMPLE_SCHEMA, **kwargs):
        """Validate answers that must fail.

        Args:
            answers: Answers to validate.
            schema: Schema to validate against.
            **kwargs: Options passed to ``validate_answers`` (``strict``).

        Returns:
            The ``field_errors`` of the raised ``AnswersValidationError``.
        """
        with self.assertRaises(AnswersValidationError) as ctx:
            validate_answers(schema, answers, **kwargs)
        return ctx.exception.field_errors

    def test_valid_answers_are_returned(self):
        """Valid answers come back as they are."""
        self.assertEqual(validate_answers(SAMPLE_SCHEMA, FULL_ANSWERS), FULL_ANSWERS)

    def test_unknown_field_id_is_an_error(self):
        """An id absent from the schema is refused."""
        errors = self.errors({"nope": 1})
        self.assertEqual(list(errors), ["nope"])

    def test_none_and_empty_string_are_ignored(self):
        """Empty answers are dropped instead of being validated."""
        cleaned = validate_answers(
            SAMPLE_SCHEMA, {"f_observation": "", "f_mesure": None, "f_niveau": "faible"}
        )
        self.assertEqual(cleaned, {"f_niveau": "faible"})

    def test_boolean_refuses_strings_and_integers(self):
        """Only a real boolean is accepted for a boolean field."""
        for value in ("true", 1, 0):
            with self.subTest(value=value):
                self.assertIn("f_acces_libre", self.errors({"f_acces_libre": value}))

    def test_boolean_accepts_false(self):
        """``False`` is an answer, not an empty value."""
        cleaned = validate_answers(SAMPLE_SCHEMA, {"f_acces_libre": False})
        self.assertEqual(cleaned, {"f_acces_libre": False})

    def test_number_refuses_booleans_and_strings(self):
        """A boolean or a numeric string is not a number."""
        for value in (True, "12"):
            with self.subTest(value=value):
                self.assertIn("f_mesure", self.errors({"f_mesure": value}))

    def test_number_bounds_are_inclusive(self):
        """The minimum and the maximum themselves are accepted, including 0."""
        for value in (0, 100, 12.5):
            with self.subTest(value=value):
                cleaned = validate_answers(SAMPLE_SCHEMA, {"f_mesure": value})
                self.assertEqual(cleaned, {"f_mesure": value})

    def test_number_outside_bounds_is_refused(self):
        """A value under the minimum or over the maximum is refused."""
        for value in (-1, 101):
            with self.subTest(value=value):
                self.assertIn("f_mesure", self.errors({"f_mesure": value}))

    def test_select_outside_options_is_refused(self):
        """An option that is not listed in the field is refused."""
        self.assertIn("f_niveau", self.errors({"f_niveau": "extrême"}))

    def test_text_must_be_a_string(self):
        """A number is not accepted for a text field."""
        self.assertIn("f_observation", self.errors({"f_observation": 12}))

    def test_text_length_limit(self):
        """A text of ``TEXT_MAX_LENGTH`` characters passes, one more is refused."""
        validate_answers(SAMPLE_SCHEMA, {"f_observation": "a" * TEXT_MAX_LENGTH})
        too_long = "a" * (TEXT_MAX_LENGTH + 1)
        self.assertEqual(TEXT_MAX_LENGTH + 1, 5001)
        self.assertIn("f_observation", self.errors({"f_observation": too_long}))

    def test_one_message_per_invalid_field(self):
        """Several invalid answers give one message each, keyed by field id."""
        errors = self.errors({"f_mesure": 500, "f_niveau": "x", "nope": 1})
        self.assertEqual(set(errors), {"f_mesure", "f_niveau", "nope"})

    def test_answers_must_be_a_dict(self):
        """Answers that are not an object give a global ``__all__`` error."""
        for value in (["a"], "text", None):
            with self.subTest(value=value):
                self.assertEqual(list(self.errors(value)), ["__all__"])

    def test_error_is_a_django_validation_error(self):
        """``AnswersValidationError`` can be caught as a Django ``ValidationError``."""
        from django.core.exceptions import ValidationError

        self.assertTrue(issubclass(AnswersValidationError, ValidationError))


class ValidateAnswersStrictTests(SimpleTestCase):
    """``validate_answers(strict=True)``, used when the visit is finished."""

    def test_missing_required_field_is_an_error(self):
        """A required field without answer is reported."""
        with self.assertRaises(AnswersValidationError) as ctx:
            validate_answers(SAMPLE_SCHEMA, {"f_acces_libre": True}, strict=True)
        self.assertEqual(
            set(ctx.exception.field_errors),
            {"f_observation", "f_niveau", "f_mesure"},
        )

    def test_optional_field_may_be_missing(self):
        """A field with ``required=False`` can stay empty."""
        cleaned = validate_answers(SAMPLE_SCHEMA, FULL_ANSWERS, strict=True)
        self.assertNotIn("f_remarques", cleaned)

    def test_required_defaults_to_true(self):
        """A field without a ``required`` key is considered required."""
        schema = deepcopy(SAMPLE_SCHEMA)
        del schema["sections"][1]["fields"][2]["required"]
        with self.assertRaises(AnswersValidationError) as ctx:
            validate_answers(schema, FULL_ANSWERS, strict=True)
        self.assertEqual(list(ctx.exception.field_errors), ["f_remarques"])

    def test_invalid_field_has_a_single_message(self):
        """An invalid required field is not reported a second time as missing."""
        with self.assertRaises(AnswersValidationError) as ctx:
            validate_answers(
                SAMPLE_SCHEMA, {**FULL_ANSWERS, "f_mesure": 500}, strict=True
            )
        self.assertEqual(list(ctx.exception.field_errors), ["f_mesure"])
        self.assertNotIn("obligatoire", ctx.exception.field_errors["f_mesure"])

    def test_non_strict_does_not_require_anything(self):
        """Without ``strict``, empty answers are fine."""
        self.assertEqual(validate_answers(SAMPLE_SCHEMA, {}), {})


class ComputeProgressTests(SimpleTestCase):
    """``compute_progress`` figures, globally and by section."""

    def test_schema_without_field(self):
        """A schema with no field has a progress of 0 and no division by zero."""
        progress = compute_progress({"sections": []}, {})
        self.assertEqual(progress["total"], 0)
        self.assertEqual(progress["pct"], 0)
        self.assertEqual(progress["by_section"], [])

    def test_empty_answers(self):
        """Without answer, every required field is missing."""
        progress = compute_progress(SAMPLE_SCHEMA, {})
        self.assertEqual(
            (progress["done"], progress["total"], progress["pct"]), (0, 5, 0)
        )
        self.assertEqual(progress["missing_required"], 4)

    def test_complete_answers(self):
        """With every field answered, the visit is at 100 %."""
        progress = compute_progress(SAMPLE_SCHEMA, {**FULL_ANSWERS, "f_remarques": "x"})
        self.assertEqual(progress["pct"], 100)
        self.assertEqual(progress["missing_required"], 0)
        self.assertTrue(all(s["complete"] for s in progress["by_section"]))

    def test_percentage_is_rounded(self):
        """One answer out of three gives 33 %."""
        schema = {
            "sections": [
                {
                    "id": "s",
                    "title": "S",
                    "order": 1,
                    "fields": [
                        {"id": f"f{i}", "label": "l", "type": "text", "order": i}
                        for i in range(3)
                    ],
                }
            ]
        }
        self.assertEqual(compute_progress(schema, {"f0": "x"})["pct"], 33)

    def test_sections_are_sorted_by_order(self):
        """The sections of the result follow their ``order`` key."""
        schema = deepcopy(SAMPLE_SCHEMA)
        schema["sections"][0]["order"] = 3
        ids = [s["id"] for s in compute_progress(schema, {})["by_section"]]
        self.assertEqual(ids, ["s_mesures", "s_general"])

    def test_section_figures(self):
        """Each section reports its own done/total/missing/complete values."""
        progress = compute_progress(SAMPLE_SCHEMA, {"f_acces_libre": True})
        general, mesures = progress["by_section"]
        self.assertEqual((general["done"], general["total"]), (1, 2))
        self.assertEqual(general["missing_required"], 1)
        self.assertFalse(general["complete"])
        self.assertEqual(mesures["missing_required"], 2)
        self.assertEqual(mesures["title"], "Mesures")

    def test_false_and_zero_count_as_answers(self):
        """``False`` and ``0`` are answers, only ``None`` and ``""`` are empty."""
        progress = compute_progress(
            SAMPLE_SCHEMA, {"f_acces_libre": False, "f_mesure": 0}
        )
        self.assertEqual(progress["done"], 2)

    def test_empty_values_do_not_count(self):
        """``None`` and an empty string are not answers."""
        progress = compute_progress(
            SAMPLE_SCHEMA, {"f_observation": "", "f_niveau": None}
        )
        self.assertEqual(progress["done"], 0)

    def test_non_dict_answers_are_tolerated(self):
        """Corrupted answers (not a dict) are treated as empty."""
        self.assertEqual(compute_progress(SAMPLE_SCHEMA, None)["done"], 0)
        self.assertEqual(compute_progress(SAMPLE_SCHEMA, ["x"])["done"], 0)
