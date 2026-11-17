"""Helpers shared by the forms of the apps: widget styling and address autocomplete."""

from typing import Any, ClassVar

from django import forms
from django.urls import reverse_lazy


def enable_address_autocomplete(form: forms.BaseForm) -> None:
    """Make the street field of a form suggest addresses while the user types.

    The field asks ``core:address_suggestions`` (HTMX) and the suggestions only
    pre-fill the street, postal code and city: the coordinates are always computed
    by the server on save (``certify_address``).

    Args:
        form: Form with an ``address_line`` field.
    """
    field = form.fields.get("address_line")
    if field is None:
        return
    field.widget.attrs.update(
        {
            "autocomplete": "off",
            "hx-get": reverse_lazy("core:address_suggestions"),
            "hx-trigger": "input changed delay:300ms",
            "hx-target": "#address-suggestions",
            "hx-swap": "innerHTML",
        }
    )


class StyledFormMixin:
    """Give every widget the shared input class and the placeholders of the form.

    Put it before the Django form class in the bases. File inputs, checkboxes and
    radio buttons keep their own look.

    Attributes:
        input_class: CSS class of the inputs (``form-input``, see ``styles.css``).
        placeholders: Example placeholder of the fields, by field name.
    """

    input_class: ClassVar[str] = "form-input"
    placeholders: ClassVar[dict[str, str]] = {}
    UNSTYLED_WIDGETS = (
        forms.FileInput,
        forms.CheckboxInput,
        forms.CheckboxSelectMultiple,
        forms.RadioSelect,
    )

    # Type-only: provided by the form class this mixin is combined with.
    fields: dict[str, forms.Field]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Style the widgets once the fields exist.

        Args:
            *args: Positional arguments passed to the form.
            **kwargs: Keyword arguments passed to the form.
        """
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, self.UNSTYLED_WIDGETS):
                field.widget.attrs["class"] = self.input_class
            if name in self.placeholders:
                field.widget.attrs["placeholder"] = self.placeholders[name]
