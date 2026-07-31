from django import forms
from .models import InspectionFolder

class InspectionFolderForm(forms.ModelForm):
    class Meta:
        model = InspectionFolder
        fields = ["company"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Application de la classe CSS sur les champs
        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})

        # Configuration du choix de société
        company_field = self.fields.get("company")
        if isinstance(company_field, forms.ModelChoiceField):
            company_field.empty_label = "Sélectionnez une société"