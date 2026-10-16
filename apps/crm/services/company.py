"""Company services: INSEE Sirene API client, getters and filtered lists."""

import os

import requests
from django.conf import settings
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from crm.models import Company


class INSEEApiClient:
    """Client of the INSEE Sirene API, used to retrieve company data.

    Attributes:
        BASE_URL: Root URL of the Sirene API.
    """

    BASE_URL = "https://api.insee.fr/api-sirene/3.11"

    @classmethod
    def get_headers(cls) -> dict:
        """Build the request headers, with the API key from the settings or the environment.

        Returns:
            The headers to send to the Sirene API.
        """
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
        """Query the INSEE API by SIRET and return cleaned company data.

        Network errors and unsuccessful responses are swallowed.

        Args:
            siret: SIRET number of the establishment (14 digits).

        Returns:
            The data formatted by ``_format_etablissement_data``, or None if the
            establishment is not found or the API cannot be reached.
        """
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
        """Turn the raw INSEE establishment JSON into a clean dictionary.

        Builds the company name and the full address, and computes the VAT number
        from the SIREN.

        Args:
            etab: Establishment as returned by the Sirene API.
            siret_fallback: SIRET used when the response does not contain one.

        Returns:
            A dict with ``name``, ``siren``, ``siret``, ``vat_number``,
            ``legal_structure``, ``company_size_category``, ``business_line``,
            ``address`` and ``creation_date``.
        """
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


def get_company_by_id(pk: int) -> Company:
    """Return a company with its tracking users.

    Not yet filtered by user.

    Args:
        pk: Primary key of the company.

    Returns:
        The company.

    Raises:
        Http404: If the company does not exist.
    """
    return get_object_or_404(
        Company.objects.select_related("created_by", "updated_by", "archived_by"), pk=pk
    )


def get_company_archive_impact(company: Company) -> dict[str, QuerySet]:
    """Describe what archiving a company does.

    Args:
        company: Company about to be archived.

    Returns:
        A dict with:

        - ``contacts``: active contacts that will be archived with it,
        - ``kept_contacts``: active contacts left active because an active folder
          references them,
        - ``folders``: active folders of the company, which are not archived.
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


def get_filtered_companies(request: HttpRequest) -> QuerySet:
    """Return the companies filtered and sorted by the GET parameters.

    Args:
        request: Current request. Reads ``q`` (search on name, SIREN, SIRET and
            reference), ``status`` (``active`` by default, or ``archived``) and
            ``sort`` (``name``, ``-created_at`` or ``-inspection_folders_count``,
            anything else falls back to ``name``).

    Returns:
        The companies, annotated with ``inspection_folders_count``.
    """
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
