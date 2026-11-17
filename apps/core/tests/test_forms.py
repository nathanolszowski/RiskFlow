"""Tests for the shared form helpers (``core/forms.py``)."""

from django import forms
from django.test import SimpleTestCase

from core.forms import StyledFormMixin


class SampleForm(StyledFormMixin, forms.Form):
    """Form with a text input, a checkbox and a file input."""

    placeholders = {"name": "ex: ACME"}

    name = forms.CharField()
    agreed = forms.BooleanField(required=False)
    attachment = forms.FileField(required=False)


class CompactForm(SampleForm):
    """Same form with another input class."""

    input_class = "compact"


class StyledFormMixinTests(SimpleTestCase):
    """``StyledFormMixin``."""

    def test_inputs_get_the_class_and_the_placeholder(self):
        """Text inputs get ``form-input`` and their placeholder."""
        attrs = SampleForm().fields["name"].widget.attrs
        self.assertEqual(
            (attrs["class"], attrs["placeholder"]), ("form-input", "ex: ACME")
        )

    def test_checkboxes_and_files_keep_their_look(self):
        """Checkboxes and file inputs are not styled as text inputs."""
        form = SampleForm()
        self.assertNotIn("class", form.fields["agreed"].widget.attrs)
        self.assertNotIn("class", form.fields["attachment"].widget.attrs)

    def test_input_class_can_be_overridden(self):
        """A form can use its own input class."""
        self.assertEqual(CompactForm().fields["name"].widget.attrs["class"], "compact")
