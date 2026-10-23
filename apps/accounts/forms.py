"""Forms of the profile page."""

from core.forms import enable_address_autocomplete
from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from .models import CustomUser

INPUT_CLASS = (
    "w-full rounded-lg border border-border-default bg-surface-secondary px-3 py-2 "
    "text-xs text-text-main placeholder:text-text-muted focus:border-brand-primary "
    "focus:ring-1 focus:ring-brand-primary focus:outline-none transition"
)


class StyledFormMixin:
    """Give every widget of the form the shared input classes."""

    def __init__(self, *args, **kwargs):
        """Apply the input classes once the fields exist."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS


class EmailForm(StyledFormMixin, forms.ModelForm):
    """Edit the e-mail address (required here, optional on the model)."""

    email = forms.EmailField(label="Nouvelle adresse e-mail")

    class Meta:
        """Bind the form to the user model."""

        model = CustomUser
        fields = ["email"]


class AddressForm(StyledFormMixin, forms.ModelForm):
    """Edit the home address."""

    class Meta:
        """Bind the form to the address fields."""

        model = CustomUser
        fields = ["address_line", "address_complement", "postal_code", "city"]
        widgets = {
            "address_line": forms.TextInput(attrs={"autocomplete": "address-line1"}),
            "address_complement": forms.TextInput(
                attrs={
                    "autocomplete": "address-line2",
                    "placeholder": "Bâtiment, étage, digicode…",
                }
            ),
            "postal_code": forms.TextInput(
                attrs={"autocomplete": "postal-code", "inputmode": "numeric"}
            ),
            "city": forms.TextInput(attrs={"autocomplete": "address-level2"}),
        }

    def __init__(self, *args, **kwargs):
        """Make the street, postal code and city mandatory once the form is used."""
        super().__init__(*args, **kwargs)
        for name in ("address_line", "postal_code", "city"):
            self.fields[name].required = True
        enable_address_autocomplete(self)


class ProfilePasswordForm(StyledFormMixin, PasswordChangeForm):
    """Password change form with French labels and the shared input classes."""

    def __init__(self, *args, **kwargs):
        """Relabel the fields."""
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Mot de passe actuel"
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmer le nouveau mot de passe"
        self.fields["new_password1"].help_text = ""
