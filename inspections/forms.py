from django import forms
from .models import InspectionFolder

class InspectionFolderForm(forms.ModelForm):
    class Meta:
        model = InspectionFolder
        fields = [
                'company',
                'contact',
                'current_phase',
                'inspection_site_address',
                'notes',
            ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})

        company_field = self.fields.get("company")
        if isinstance(company_field, forms.ModelChoiceField):
            company_field.empty_label = "Sélectionnez une société"