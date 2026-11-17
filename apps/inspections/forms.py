"""Forms of the inspections app: folders, visits and recommendations."""

from typing import TYPE_CHECKING, Any, cast

from core.forms import StyledFormMixin, enable_address_autocomplete
from django import forms
from django.db.models import Q
from django.urls import reverse

from .models import InspectionFolder, Recommandation, VisitInstance, VisitTemplate
from .services.template import get_usable_templates

if TYPE_CHECKING:
    from collections.abc import Iterable

    from accounts.models import CustomUser
    from django.db.models import Model


class InspectionFolderForm(StyledFormMixin, forms.ModelForm):
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
        """Set the initial phase of a new folder and limit the contacts to the company.

        Args:
            *args: Positional arguments passed to ``ModelForm``.
            company: Company the folder is created for, if known: the contacts are then
                limited to its own active ones. Archived companies are never offered. Without it, a new folder offers no contact until a
                company is chosen (the company field reloads the contact field).
            **kwargs: Keyword arguments passed to ``ModelForm``.
        """
        super().__init__(*args, **kwargs)

        contact_field = self.fields.get("contact")
        if (
            isinstance(contact_field, forms.ModelChoiceField)
            and contact_field.queryset is not None
        ):
            if company:
                contact_field.queryset = contact_field.queryset.filter(
                    company=company, is_active=True
                )
                contact_field.empty_label = "Aucun contact référent"
            elif not self.instance.pk:
                contact_field.queryset = contact_field.queryset.none()
                contact_field.empty_label = "Sélectionnez d'abord un client"

        # A new folder skips the CREATION phase and starts directly at PREPARATION
        if not self.instance.pk:
            self.instance.current_phase = InspectionFolder.Phase.PREPARATION

        enable_address_autocomplete(self)

        company_field = self.fields.get("company")
        if (
            isinstance(company_field, forms.ModelChoiceField)
            and company_field.queryset is not None
        ):
            company_field.empty_label = "Sélectionnez un client"
            # A folder is never created for an archived company
            company_field.queryset = company_field.queryset.filter(is_active=True)
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

    The company is fixed and the contact is limited to the active contacts of the
    company, plus the current one.
    The transient ``CREATION`` phase and the ``ARCHIVED`` phase are not selectable,
    unless the folder is in it.
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

        # CREATION is transient and ARCHIVED is set by archiving, not by hand: neither
        # is selectable, unless the folder is still in it
        hidden = {InspectionFolder.Phase.CREATION, InspectionFolder.Phase.ARCHIVED}
        phase_field = cast("forms.ChoiceField", self.fields["current_phase"])
        phase_field.choices = [
            (value, label)
            for value, label in cast("Iterable[tuple[Any, Any]]", phase_field.choices)
            if value not in hidden or value == self.instance.current_phase
        ]

        contact_field = self.fields.get("contact")
        if self.instance.pk and isinstance(contact_field, forms.ModelChoiceField):
            # Archived contacts are not offered, except the current one of the folder
            contact_field.queryset = self.instance.company.contacts.filter(
                Q(is_active=True) | Q(pk=self.instance.contact_id)
            ).order_by("last_name", "first_name")
            contact_field.empty_label = "Aucun contact référent"


class VisitInstanceUpdateForm(StyledFormMixin, forms.ModelForm):
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


class VisitCreateForm(StyledFormMixin, forms.Form):
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
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": "Indiquez la date de la visite."},
    )
    due_time = forms.TimeField(
        label="Heure de rendez-vous",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )

    def __init__(self, *args: Any, user: "CustomUser", **kwargs: Any) -> None:
        """Limit the template choices to the ones usable by the user.

        Args:
            *args: Positional arguments passed to ``Form``.
            user: User preparing the visit.
            **kwargs: Keyword arguments passed to ``Form``.
        """
        super().__init__(*args, **kwargs)
        template_field = cast("forms.ModelChoiceField", self.fields["template"])
        template_field.queryset = get_usable_templates(user)


class RecommandationUpdateForm(StyledFormMixin, forms.ModelForm):
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


class RecommandationCreateForm(RecommandationUpdateForm):
    """Create a recommendation: the status is not asked, a new one is open."""

    class Meta(RecommandationUpdateForm.Meta):
        fields = ["topic", "description", "priority", "due_date", "notes"]
