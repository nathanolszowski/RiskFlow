from django import forms
from .models import Company


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
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
            "name": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "Ex: RiskFlow SAS",
            }),
            "siren": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "123456789",
                "maxlength": "9",
            }),
            "siret": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "12345678900012",
                "maxlength": "14",
            }),
            "vat_number": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "FR12345678901",
            }),
            "business_line": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "Ex: Industrie, Conseil...",
            }),
            "legal_structure": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "Ex: SAS, SARL, SA...",
            }),
            "company_size_category": forms.TextInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "Ex: PME, ETI, Grande entreprise...",
            }),
            "nb_employees": forms.NumberInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "45",
            }),
            "creation_date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:ring-indigo-500",
            }),
            "website": forms.URLInput(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "placeholder": "https://www.entreprise.com",
            }),
            "address": forms.Textarea(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "rows": 2,
                "placeholder": "Adresse complète du siège...",
            }),
            "labels": forms.Textarea(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "rows": 2,
                "placeholder": "ISO 9001, MASE, etc.",
            }),
            "executive_board": forms.Textarea(attrs={
                "class": "w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500",
                "rows": 2,
                "placeholder": "Membres du conseil d'administration / dirigeants...",
            }),
        }