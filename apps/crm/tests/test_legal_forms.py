"""Tests for the legal forms table (crm/services/legal_forms.py)."""

from django.test import SimpleTestCase

from crm.services.legal_forms import LEGAL_FORMS, legal_form_label


class LegalFormLabelTests(SimpleTestCase):
    """``legal_form_label`` and the table behind it."""

    def test_known_code(self):
        """A Sirene code gives its label."""
        self.assertEqual(
            legal_form_label("5499"),
            "Société à responsabilité limitée (sans autre indication)",
        )
        self.assertEqual(
            legal_form_label("5710"), "SAS, société par actions simplifiée"
        )

    def test_unknown_code_is_returned_as_is(self):
        """A code missing from the table is shown unchanged."""
        self.assertEqual(legal_form_label("1234"), "1234")

    def test_free_text_is_returned_as_is(self):
        """A legal form typed by hand is shown unchanged."""
        self.assertEqual(legal_form_label("SAS"), "SAS")

    def test_spaces_are_stripped(self):
        """Spaces around a code do not prevent the match."""
        self.assertEqual(legal_form_label(" 5710 "), LEGAL_FORMS["5710"])

    def test_empty_values(self):
        """An empty value or None gives an empty string."""
        self.assertEqual(legal_form_label(""), "")
        self.assertEqual(legal_form_label(None), "")

    def test_table_shape(self):
        """Every key is a four-digit code and every label is filled."""
        self.assertGreater(len(LEGAL_FORMS), 100)
        for code, label in LEGAL_FORMS.items():
            with self.subTest(code=code):
                self.assertRegex(code, r"^\d{4}$")
                self.assertTrue(label.strip())
