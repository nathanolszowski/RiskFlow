"""Forms of the inspections app: folders, visits and recommendations."""

from typing import TYPE_CHECKING, Any

from core.forms import enable_address_autocomplete
from django import forms
from django.urls import reverse

from .models import InspectionFolder, Recommandation, VisitInstance, VisitTemplate
from .services.template import get_usable_templates

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models import Model


class InspectionFolderForm(forms.ModelForm):
    """Create a folder: company, referent contact, site address and notes.

    A new folder skips the ``CREATION`` phase and starts at ``PREPARATION``.
    """

    class Meta:
        model = InspectionFolder
        fields = [
            "company",
            "contact",
            "address_line",
            "postal_code",
            "city",
            "notes",
        ]

    def __init__(
        self,
        *args: Any,
        company: "Model | None" = None,
        **kwargs: Any,
    ) -> None:
        """Set the initial phase of a new folder and style the widgets.

        Args:
            *args: Positional arguments passed to ``ModelForm``.
            company: Company the folder is created for, if known: the contacts are then
                limited to its own. Without it, a new folder offers no contact until a
                company is chosen (the company field reloads the contact field).
            **kwargs: Keyword arguments passed to ``ModelForm``.
        """
        super().__init__(*args, **kwargs)

        contact_field = self.fields.get("contact")
        if isinstance(contact_field, forms.ModelChoiceField):
            if company:
                contact_field.queryset = contact_field.queryset.filter(company=company)
                contact_field.empty_label = "Aucun contact référent"
            elif not self.instance.pk:
                contact_field.queryset = contact_field.queryset.none()
                contact_field.empty_label = "Sélectionnez d'abord un client"

        # A new folder skips the CREATION phase and starts directly at PREPARATION
        if not self.instance.pk:
            self.instance.current_phase = InspectionFolder.Phase.PREPARATION

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})
        enable_address_autocomplete(self)

        company_field = self.fields.get("company")
        if isinstance(company_field, forms.ModelChoiceField):
            company_field.empty_label = "Sélectionnez un client"
            # Choosing a company reloads the contact field with the contacts of that company
            company_field.widget.attrs.update(
                {
                    "hx-get": reverse("inspections:folder_contact_field"),
                    "hx-trigger": "change",
                    "hx-target": "#contact-field",
                    "hx-swap": "innerHTML",
                }
            )


class InspectionFolderUpdateForm(InspectionFolderForm):
    """Edit form for an existing folder.

    The company is fixed and the contact is limited to the contacts of the company.
    The transient ``CREATION`` phase is not selectable.
    """

    class Meta(InspectionFolderForm.Meta):
        fields = [
            "contact",
            "current_phase",
            "address_line",
            "postal_code",
            "city",
            "notes",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Restrict the phase choices and the contact queryset.

        Args:
            *args: Positional arguments passed to ``InspectionFolderForm``.
            **kwargs: Keyword arguments passed to ``InspectionFolderForm``.
        """
        super().__init__(*args, **kwargs)

        # CREATION is only a transient phase: not selectable (unless the folder is still in it)
        phase_field = self.fields["current_phase"]
        phase_field.choices = [
            (value, label)
            for value, label in phase_field.choices
            if value != InspectionFolder.Phase.CREATION
            or value == self.instance.current_phase
        ]

        contact_field = self.fields.get("contact")
        if self.instance.pk and isinstance(contact_field, forms.ModelChoiceField):
            contact_field.queryset = self.instance.company.contacts.order_by(
                "last_name", "first_name"
            )
            contact_field.empty_label = "Aucun contact référent"


class VisitInstanceUpdateForm(forms.ModelForm):
    """Edit form for the planning data of a visit: date, appointment time and notes.

    The status is not edited here: see ``set_visit_done``.
    """

    class Meta:
        model = VisitInstance
        fields = [
            "due_date",
            "due_time",
            "notes",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Style the widgets.

        Args:
            *args: Positional arguments passed to ``ModelForm``.
            **kwargs: Keyword arguments passed to ``ModelForm``.
        """
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})


class VisitCreateForm(forms.Form):
    """Preparation of a visit: a usable template (own or shared) and a date.

    Attributes:
        template: Template to start from, among the ones the user can use.
        due_date: Planned date of the visit.
        due_time: Appointment time, optional.
    """

    template = forms.ModelChoiceField(
        queryset=VisitTemplate.objects.none(),
        empty_label=None,
        label="Template",
        error_messages={
            "required": "Choisissez un template.",
            "invalid_choice": "Ce template n'est pas disponible.",
        },
    )
    due_date = forms.DateField(
        label="Date de la visite",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"
        ),
        error_messages={"required": "Indiquez la date de la visite."},
    )
    due_time = forms.TimeField(
        label="Heure de rendez-vous",
        required=False,
        widget=forms.TimeInput(
            attrs={"type": "time", "class": "form-input"}, format="%H:%M"
        ),
    )

    def __init__(self, *args: Any, user: "CustomUser", **kwargs: Any) -> None:
        """Limit the template choices to the ones usable by the user.

        Args:
            *args: Positional arguments passed to ``Form``.
            user: User preparing the visit.
            **kwargs: Keyword arguments passed to ``Form``.
        """
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = get_usable_templates(user)


class RecommandationUpdateForm(forms.ModelForm):
    """Create or edit a recommendation: topic, description, priority, status, date and notes."""

    class Meta:
        model = Recommandation
        fields = [
            "topic",
            "description",
            "priority",
            "current_status",
            "due_date",
            "notes",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Style the widgets.

        Args:
            *args: Positional arguments passed to ``ModelForm``.
            **kwargs: Keyword arguments passed to ``ModelForm``.
        """
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})
