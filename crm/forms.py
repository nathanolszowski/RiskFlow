from django import forms
from .models import Company, Contact

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "reference",
            "name",
            "siren",
            "siret",
            "vat_number",
            "business_line",
            "legal_structure",
            "company_size_category",
            "nb_employees",
            "creation_date",
            "website",
            "address",
            "labels",
            "executive_board",
        ]
        widgets = {
            "creation_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "address": forms.Textarea(attrs={"rows": 2}),
            "labels": forms.Textarea(attrs={"rows": 2}),
            "executive_board": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            for field in self.fields.values():
                field.widget.attrs["class"] = "form-input"

            placeholders = {
                "name": "ex: ACME Industries",
                "siren": "ex: 775652126",
                "siret": "ex: 77565212602114",
                "vat_number": "ex: FR12775652126",
                "legal_structure": "ex: SAS, SARL...",
                "business_line": "ex: Industrie métallurgique",
                "company_size_category": "ex: PME / ETI / GE",
                "nb_employees": "ex: 50",
                "creation_date": "ex: 2015-06-12",
                "website": "ex: https://www.exemple.fr",
                "address": "ex: 12 Rue de la Paix, 75000 Paris",
                "labels": "ex: ISO 9001, ISO 27001",
                "executive_board": "ex: Jean Dupont (PDG)",
            }
            for field_name, placeholder_text in placeholders.items():
                field = self.fields.get(field_name)
                if field:
                    field.widget.attrs["placeholder"] = placeholder_text


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "company",
            "first_name",
            "last_name",
            "email",
            "phone_number_fix",
            "phone_number_mobile",
            "position",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-input"})

        company_field = self.fields.get("company")
        if isinstance(company_field, forms.ModelChoiceField):
            company_field.empty_label = "Sélectionnez une société"
        # Placeholders
        placeholders = {
            "first_name": "ex: Jean",
            "last_name": "ex: Dupont",
            "email": "jean.dupont@exemple.fr",
            "phone_number_fix": "ex: 01 23 45 67 89",
            "phone_number_mobile": "ex: 06 12 34 56 78",
            "position": "ex: Responsable Achat",
        }
        for field_name, placeholder_text in placeholders.items():
            field = self.fields.get(field_name)
            if field:
                field.widget.attrs["placeholder"] = placeholder_text