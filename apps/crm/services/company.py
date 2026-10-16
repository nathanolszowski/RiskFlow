import os

import requests
from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from crm.models import Company


class INSEEApiClient:
    """Client to interact with the INSEE SIRENE API for company data retrieval."""

    BASE_URL = "https://api.insee.fr/api-sirene/3.11"

    @classmethod
    def get_headers(cls) -> dict:
        api_key = getattr(settings, "INSEE_API_KEY", None) or os.getenv(
            "INSEE_API_KEY", ""
        )
        return {
            "X-INSEE-Api-Key-Integration": api_key,
            "Accept": "application/json",
            "User-Agent": "DjangoCRM/1.0",
        }

    @classmethod
    def fetch_by_siret(cls, siret: str) -> dict | None:
        """Interroge l'API INSEE par SIRET et retourne un dictionnaire nettoyé ou None."""
        url = f"{cls.BASE_URL}/siret/{siret}"
        try:
            response = requests.get(url, headers=cls.get_headers(), timeout=5)

            if response.status_code == 200:
                data = response.json()
                etablissement = data.get("etablissement")
                # Fallback
                if not etablissement and "etablissements" in data:
                    etablissements = data.get("etablissements", [])
                    etablissement = etablissements[0] if etablissements else None
                if etablissement:
                    return cls._format_etablissement_data(etablissement, siret)
        except requests.RequestException:
            pass
        return None

    @staticmethod
    def _format_etablissement_data(etab: dict, siret_fallback: str) -> dict:
        """Méthode privée servant à transformer le JSON brut INSEE en un dictionnaire propre."""
        unit = etab.get("uniteLegale", {})
        address = etab.get("adresseEtablissement", {})
        periodes = etab.get("periodesEtablissement", [{}])
        actual_period = periodes[0] if periodes else {}
        # Name formatting
        name = (
            unit.get("denominationUniteLegale")
            or f"{unit.get('prenomUsuelUniteLegale', '')} {unit.get('nomUniteLegale', '')}".strip()
        )
        # Address formatting
        num = address.get("numeroVoieEtablissement") or ""
        type_v = address.get("typeVoieEtablissement") or ""
        lib_v = address.get("libelleVoieEtablissement") or ""
        cp = address.get("codePostalEtablissement") or ""
        ville = address.get("libelleCommuneEtablissement") or ""

        address_parts = [
            p for p in [f"{num} {type_v} {lib_v}".strip(), f"{cp} {ville}".strip()] if p
        ]
        full_address = ", ".join(address_parts)
        # SIREN & VAT number calculation
        siren = etab.get("siren") or (
            siret_fallback[:9] if len(siret_fallback) == 14 else ""
        )
        vat_number = ""
        if siren and siren.isdigit() and len(siren) == 9:
            vat_key = (12 + 3 * (int(siren) % 97)) % 97
            vat_number = f"FR{vat_key:02d}{siren}"

        return {
            "name": name,
            "siren": siren,
            "siret": etab.get("siret", siret_fallback),
            "vat_number": vat_number,
            "legal_structure": unit.get("categorieJuridiqueUniteLegale", ""),
            "company_size_category": unit.get("categorieEntreprise", ""),
            "business_line": actual_period.get("activitePrincipaleEtablissement")
            or unit.get("activitePrincipaleUniteLegale", ""),
            "address": full_address,
            "creation_date": etab.get("dateCreationEtablissement")
            or unit.get("dateCreationUniteLegale", ""),
        }


def get_company_by_id(pk):
    """Return a company with its tracking users, or raise a 404."""
    return get_object_or_404(
        Company.objects.select_related("created_by", "updated_by", "archived_by"), pk=pk
    )


def get_company_archive_impact(company):
    """
    Describe what archiving a company does:
    - contacts: active contacts that will be archived with it,
    - kept_contacts: active contacts left active because an active folder references them,
    - folders: active folders of the company, which are not archived.
    """
    active_contacts = company.contacts.filter(is_active=True)
    kept_contacts = active_contacts.filter(
        inspection_folders__is_active=True
    ).distinct()
    return {
        "contacts": active_contacts.exclude(pk__in=kept_contacts),
        "kept_contacts": kept_contacts,
        "folders": company.inspection_folders.filter(is_active=True),
    }


def get_filtered_companies(request):
    """Extrait les paramètres GET et renvoie le QuerySet de sociétés filtré et trié."""
    companies = Company.objects.annotate(
        inspection_folders_count=Count("inspection_folders")
    )

    # Recherche textuelle
    q = request.GET.get("q", "").strip()
    if q:
        companies = companies.filter(
            Q(name__icontains=q)
            | Q(siren__icontains=q)
            | Q(siret__icontains=q)
            | Q(reference__icontains=q)
        )

    # Filtre par statut
    status = request.GET.get("status", "active").strip()
    if status == "active":
        companies = companies.filter(is_active=True)
    elif status == "archived":
        companies = companies.filter(is_active=False)

    # Tri sécurisé
    sort_by = request.GET.get("sort", "name")
    allowed_sorts = ["name", "-created_at", "-inspection_folders_count"]

    if sort_by in allowed_sorts:
        companies = companies.order_by(sort_by)
    else:
        companies = companies.order_by("name")  # Fallback par défaut

    return companies
