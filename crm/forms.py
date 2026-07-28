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
        input_classes = (
            "w-full rounded-lg border border-gray-700 bg-gray-800/90 p-2 text-xs "
            "text-gray-100 placeholder-gray-500 focus:border-indigo-500 "
            "focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
        )
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": input_classes})
            # Optional if 'blank=False'
            if field_name not in ["name", "siren", "siret"]:
                field.required = False
        # Reference is read-only
        if "reference" in self.fields:
            self.fields["reference"].widget.attrs.update(
                {
                    "readonly": "readonly",
                    "class": input_classes
                    + " opacity-50 cursor-not-allowed bg-gray-900",
                }
            )
        # Placeholders
        self.fields["reference"].widget.attrs["placeholder"] = "REF-2024-001"
        self.fields["name"].widget.attrs["placeholder"] = "Ex: RiskFlow SAS"
        self.fields["siren"].widget.attrs.update(
            {"placeholder": "123456789", "maxlength": "9"}
        )
        self.fields["siret"].widget.attrs.update(
            {"placeholder": "12345678900012", "maxlength": "14"}
        )
        self.fields["vat_number"].widget.attrs["placeholder"] = "FR12345678901"
        self.fields["business_line"].widget.attrs["placeholder"] = (
            "Ex: Industrie, Conseil..."
        )
        self.fields["legal_structure"].widget.attrs["placeholder"] = (
            "Ex: SAS, SARL, SA..."
        )
        self.fields["company_size_category"].widget.attrs["placeholder"] = (
            "Ex: PME, ETI..."
        )
        self.fields["nb_employees"].widget.attrs["placeholder"] = "45"
        self.fields["website"].widget.attrs["placeholder"] = (
            "https://www.entreprise.com"
        )
        self.fields["address"].widget.attrs["placeholder"] = (
            "Adresse complète du siège..."
        )
        self.fields["labels"].widget.attrs["placeholder"] = "ISO 9001, MASE, etc."
        self.fields["executive_board"].widget.attrs["placeholder"] = (
            "Membres du conseil / dirigeants..."
        )

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
        # Style Tailwind
        input_classes = (
            "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm "
            "text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:ring-indigo-500"
        )
        for name, field in self.fields.items():
            field.widget.attrs.update({"class": input_classes})

        company_field = self.fields.get("company")
        if isinstance(company_field, forms.ModelChoiceField):
            company_field.empty_label = "Sélectionnez une société"
        # Placeholders
        self.fields["first_name"].widget.attrs["placeholder"] = "ex: Jean"
        self.fields["last_name"].widget.attrs["placeholder"] = "ex: Dupont"
        self.fields["email"].widget.attrs["placeholder"] = "jean.dupont@exemple.fr"
        self.fields["phone_number_fix"].widget.attrs["placeholder"] = "ex: 01 23 45 67 89"
        self.fields["phone_number_mobile"].widget.attrs["placeholder"] = "ex: 06 12 34 56 78"
        self.fields["position"].widget.attrs["placeholder"] = "ex: Responsable Achat"