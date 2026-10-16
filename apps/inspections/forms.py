from django import forms

from .models import InspectionFolder, Recommandation, VisitInstance, VisitTemplate
from .services.template import get_usable_templates


class InspectionFolderForm(forms.ModelForm):
    class Meta:
        model = InspectionFolder
        fields = [
            "company",
            "contact",
            "inspection_site_address",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # A new folder skips the CREATION phase and starts directly at PREPARATION
        if not self.instance.pk:
            self.instance.current_phase = InspectionFolder.Phase.PREPARATION

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})

        company_field = self.fields.get("company")
        if isinstance(company_field, forms.ModelChoiceField):
            company_field.empty_label = "Sélectionnez une société"


class InspectionFolderUpdateForm(InspectionFolderForm):
    """Edit form for an existing folder: company is fixed, contact limited to its contacts."""

    class Meta(InspectionFolderForm.Meta):
        fields = [
            "contact",
            "current_phase",
            "inspection_site_address",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
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
    """Edit form for the planning data of a visit (the status is not edited: see set_visit_done)."""

    class Meta:
        model = VisitInstance
        fields = [
            "due_date",
            "notes",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})


class VisitCreateForm(forms.Form):
    """Preparation of a visit: a usable template (own or shared) and a date."""

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

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = get_usable_templates(user)


class RecommandationUpdateForm(forms.ModelForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})
