"""Helpers shared by the forms of models with ``AddressMixin``."""

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
