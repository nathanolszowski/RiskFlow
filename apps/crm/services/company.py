"""Company services: INSEE Sirene API client and update, getters and filtered lists.

The Sirene part reads an establishment by SIRET (with its head office and its NAF 2025
activity), lists the differences with a client (``get_sirene_changes``), applies the ones
the user accepts (``apply_sirene_changes``) and tells whether the establishment is closed
or the company ceased (``get_cessation_alert``). Nothing there writes without the user.
"""

import os
from datetime import date
from typing import TYPE_CHECKING, Any

import requests
from core.services import update_tracked_instance
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from crm.models import Company
from crm.services.legal_forms import legal_form_label
from crm.services.naf import fetch_naf25_label

if TYPE_CHECKING:
    from accounts.models import CustomUser

# Fields of a company that come from the Sirene API (see ``INSEEApiClient._format_etablissement_data``).
# ``siret`` is left out: it is the key of the lookup and is unique, so it is never rewritten.
SIRENE_FIELDS = (
    "name",
    "address",
    "legal_structure",
    "company_size_category",
    "business_line",
    "creation_date",
    "siren",
    "vat_number",
    "activity_naf25",
    "headquarters_siret",
    "headquarters_address",
    "headquarters_state",
)

# How long a Sirene answer is reused between the SIRET search and the creation of the client
SIRENE_CACHE_SECONDS = 300


# Pseudo-field of the Sirene update: the administrative state (writes ``administrative_state``
# and ``closure_date`` together)
SIRENE_STATE_FIELD = "administrative_state"


class INSEEApiClient:
    """Client of the INSEE Sirene API, used to retrieve company data.

    ``fetch_by_siret`` returns the establishment, its administrative state, its head
    office (second request when it is another establishment) and its NAF 2025 activity.

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
    def _fetch_etablissement(cls, siret: str) -> dict | None:
        """Return the raw establishment JSON of a SIRET, or None.

        Network errors and unsuccessful responses are swallowed.

        Args:
            siret: SIRET number of the establishment (14 digits).

        Returns:
            The establishment as returned by the Sirene API, or None if it is not
            found or the API cannot be reached.
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
                    return etablissement
        except requests.RequestException:
            pass
        return None

    @classmethod
    def fetch_by_siret(cls, siret: str) -> dict | None:
        """Query the INSEE API by SIRET and return cleaned company data.

        When the establishment is not the head office, a second request reads the
        head office (SIREN + NIC of the head office, given by the legal unit).

        Args:
            siret: SIRET number of the establishment (14 digits).

        Returns:
            The data formatted by ``_format_etablissement_data``, completed with the
            head office (``headquarters_siret``, ``headquarters_address``,
            ``headquarters_state``), or None if the establishment is not found or the
            API cannot be reached.
        """
        etablissement = cls._fetch_etablissement(siret)
        if etablissement is None:
            return None
        data = cls._format_etablissement_data(etablissement, siret)
        data.update(cls._headquarters_data(etablissement, data))
        data.update(cls._activity_naf25_data(etablissement))
        return data

    @staticmethod
    def _activity_naf25_data(etab: dict) -> dict[str, str]:
        """Return the NAF 2025 main activity of an establishment, with its label.

        The code of the establishment is used when Sirene gives one, otherwise the one
        of the legal unit (the establishment one is not filled for every company yet).

        Args:
            etab: Establishment as returned by the Sirene API.

        Returns:
            ``activity_naf25`` and ``activity_naf25_label`` (empty when unknown).
        """
        code = (
            etab.get("activitePrincipaleNAF25Etablissement")
            or etab.get("uniteLegale", {}).get("activitePrincipaleNAF25UniteLegale")
            or ""
        )
        return {
            "activity_naf25": code,
            "activity_naf25_label": fetch_naf25_label(code) if code else "",
        }

    @classmethod
    def _headquarters_data(cls, etab: dict, data: dict) -> dict[str, str]:
        """Return the head office of an establishment (SIRET, address, state).

        Args:
            etab: Establishment as returned by the Sirene API.
            data: The same establishment, formatted.

        Returns:
            The three ``headquarters_*`` keys. The address and the state are empty if
            the head office could not be read.
        """
        if etab.get("etablissementSiege"):
            return {
                "headquarters_siret": data["siret"],
                "headquarters_address": data["address"],
                "headquarters_state": data["establishment_state"],
            }
        nic = etab.get("uniteLegale", {}).get("nicSiegeUniteLegale")
        siren = data["siren"]
        if not (nic and siren):
            return {
                "headquarters_siret": "",
                "headquarters_address": "",
                "headquarters_state": "",
            }
        headquarters_siret = f"{siren}{nic}"
        headquarters = cls._fetch_etablissement(headquarters_siret)
        if headquarters is None:
            return {
                "headquarters_siret": headquarters_siret,
                "headquarters_address": "",
                "headquarters_state": "",
            }
        formatted = cls._format_etablissement_data(headquarters, headquarters_siret)
        return {
            "headquarters_siret": headquarters_siret,
            "headquarters_address": formatted["address"],
            "headquarters_state": formatted["establishment_state"],
        }

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
            ``address``, ``creation_date``, and the administrative state
            (``establishment_state``, ``unit_state``, ``closure_date``). The
            head office is added by ``fetch_by_siret``.
        """
        unit = etab.get("uniteLegale", {})
        address = etab.get("adresseEtablissement", {})
        periodes = etab.get("periodesEtablissement", [{}])
        actual_period = periodes[0] if periodes else {}
        # Periods are listed newest first: the closing date is the start of the period
        # in which the establishment changed to closed (the current one only starts at the
        # last change of any other data, e.g. its activity)
        closure_date = ""
        if actual_period.get("etatAdministratifEtablissement") == "F":
            for period in periodes:
                if period.get("etatAdministratifEtablissement") != "F":
                    break
                closure_date = period.get("dateDebut") or ""
                if period.get("changementEtatAdministratifEtablissement"):
                    break
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
            # Administrative state, only used for the cessation alert (never copied into the company):
            # "F" = establishment closed, "C" = legal unit ceased, "A" = active
            "establishment_state": actual_period.get("etatAdministratifEtablissement")
            or "",
            "unit_state": unit.get("etatAdministratifUniteLegale") or "",
            "closure_date": closure_date,
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


def _sirene_value(field: str, value: Any) -> str:
    """Return a comparable string for a Sirene field (dates as ISO strings)."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def get_sirene_data(company: Company) -> dict | None:
    """Fetch the current Sirene data of a company from its SIRET.

    Args:
        company: Company to look up.

    Returns:
        The data formatted by the client, or None if the SIRET is not 14 digits, the
        establishment is not found or the API cannot be reached.
    """
    siret = (company.siret or "").strip()
    if len(siret) != 14 or not siret.isdigit():
        return None
    return INSEEApiClient.fetch_by_siret(siret)


def _display_value(field: str, labels: dict, value: str) -> str:
    """Return the text shown for a value in the update modal (choice or legal form label)."""
    if field == "legal_structure":
        return legal_form_label(value)
    return str(labels.get(value, value))


def get_sirene_changes(company: Company, data: dict) -> list[dict[str, str]]:
    """List the fields whose Sirene value differs from the one of the company.

    Only the fields coming from the API are compared, and a field the API returns
    empty is ignored: an empty answer never blanks a value. Fields with choices (head
    office state), the legal form and the NAF 2025 activity are shown with their label.
    The administrative state is added as one more line (``administrative_state``).

    Args:
        company: Company to compare.
        data: Data returned by the Sirene API.

    Returns:
        One dict per changed field, with ``field``, ``label``, ``current`` and ``new``
        (texts to display, not the stored values).
    """
    changes = []
    for field in SIRENE_FIELDS:
        new = _sirene_value(field, data.get(field))
        current = _sirene_value(field, getattr(company, field))
        if field == "activity_naf25":
            # The label travels with the code: it is also proposed when only the label is new
            new_label = _sirene_value(field, data.get("activity_naf25_label"))
            if new and (new != current or new_label != company.activity_naf25_label):
                changes.append(
                    {
                        "field": field,
                        "label": str(Company._meta.get_field(field).verbose_name),
                        "current": company.activity_naf25_display,
                        "new": f"{new_label} ({new})" if new_label else new,
                    }
                )
            continue
        if new and new != current:
            model_field = Company._meta.get_field(field)
            labels = dict(model_field.choices or ())
            changes.append(
                {
                    "field": field,
                    "label": str(model_field.verbose_name),
                    # Fields with choices (state of the head office) show their label, not the code
                    "current": _display_value(field, labels, current),
                    "new": _display_value(field, labels, new),
                }
            )
    state_change = _state_change(company, data)
    if state_change:
        changes.append(state_change)
    return changes


def _describe_state(state: str, since: date | None) -> str:
    """Return the label of an administrative state, with the closing date if known."""
    if not state:
        return "Non vérifié"
    label = str(Company.SireneState(state).label)
    if state == Company.SireneState.CLOSED and since:
        label += f" depuis le {since.strftime('%d/%m/%Y')}"
    return label


def _state_change(company: Company, data: dict) -> dict[str, str] | None:
    """Return the proposed change of administrative state, or None if there is none.

    A company never checked ("Non vérifié") gets a proposal as soon as Sirene gives a
    state, even "active": the check itself is worth recording.
    """
    state, since = get_administrative_state(data)
    current = company.administrative_state
    if not state:
        return None
    if state == current and since == company.closure_date:
        return None
    return {
        "field": SIRENE_STATE_FIELD,
        "label": "État administratif (Sirene)",
        "current": _describe_state(current, company.closure_date),
        "new": _describe_state(state, since),
    }


def apply_sirene_changes(
    company: Company, user: "CustomUser", data: dict, selected: list[str]
) -> list[str]:
    """Update the selected fields of a company with Sirene data.

    The selection is checked against ``SIRENE_FIELDS`` (plus the administrative state)
    and against the fields that really changed, and the values come from ``data``,
    never from the request: no other field can be written through this. Accepting the
    state also writes the closing date, accepting the NAF 2025 code also writes its
    label.

    Args:
        company: Company to update.
        user: User applying the update, recorded as ``updated_by``.
        data: Fresh data returned by the Sirene API.
        selected: Names of the fields the user accepted.

    Returns:
        The names of the fields that were updated.

    Raises:
        ValidationError: If a value cannot be stored (e.g. an unreadable date).
    """
    changed = {c["field"] for c in get_sirene_changes(company, data)}
    fields = [
        f
        for f in (*SIRENE_FIELDS, SIRENE_STATE_FIELD)
        if f in selected and f in changed
    ]
    if not fields:
        return []

    values: dict[str, Any] = {}
    for field in fields:
        if field == SIRENE_STATE_FIELD:
            state, since = get_administrative_state(data)
            values["administrative_state"] = state
            values["closure_date"] = since
            setattr(company, "administrative_state", state)
            setattr(company, "closure_date", since)
            continue
        if field == "activity_naf25":
            values["activity_naf25_label"] = _sirene_value(
                field, data.get("activity_naf25_label")
            )
            setattr(company, "activity_naf25_label", values["activity_naf25_label"])
        value: Any = _sirene_value(field, data.get(field))
        if field == "creation_date":
            try:
                value = date.fromisoformat(value)
            except ValueError:
                raise ValidationError(
                    f"{Company._meta.get_field(field).verbose_name} : date illisible."
                )
        values[field] = value
        setattr(company, field, value)

    # Validate only the fields being written (the others may be legitimately incomplete)
    company.clean_fields(
        exclude=[f.name for f in Company._meta.fields if f.name not in values]
    )
    update_tracked_instance(company, user, **values)
    return fields


def get_administrative_state(data: dict) -> tuple[str, date | None]:
    """Read the administrative state from Sirene data.

    Args:
        data: Data returned by the Sirene API (see ``get_sirene_data``).

    Returns:
        ``(state, closing date)``: ``"C"`` if the legal unit ceased, ``"F"`` if the
        establishment is closed (with its closing date, None when unknown), ``"A"`` if
        active, and an empty state when the API says nothing.
    """
    if data.get("unit_state") == "C":
        return Company.SireneState.CEASED.value, None
    if data.get("establishment_state") == "F":
        try:
            since = date.fromisoformat(data.get("closure_date") or "")
        except ValueError:
            since = None
        return Company.SireneState.CLOSED.value, since
    if data.get("establishment_state") or data.get("unit_state"):
        return Company.SireneState.ACTIVE.value, None
    return "", None


def get_cessation_alert(data: dict) -> dict[str, Any] | None:
    """Tell whether Sirene data report the company as closed or ceased.

    Read-only and informative: nothing is written on the company.

    Args:
        data: Data returned by the Sirene API (see ``get_sirene_data``).

    Returns:
        None if there is nothing to report, otherwise a dict with ``kind``
        (``"ceased"`` for the whole company, ``"closed"`` for this establishment only)
        and ``since`` (closing date, or None when unknown), plus the state and address
        of the head office (``hq_state``, ``hq_address``).
    """
    state, since = get_administrative_state(data)
    hq = {
        "hq_state": data.get("headquarters_state", ""),
        "hq_address": data.get("headquarters_address", ""),
    }
    if state == Company.SireneState.CEASED:
        return {"kind": "ceased", "since": None, **hq}
    if state == Company.SireneState.CLOSED:
        return {"kind": "closed", "since": since, **hq}
    return None


def get_sirene_data_cached(siret: str) -> dict | None:
    """Return Sirene data for a SIRET, reusing a recent answer.

    The SIRET search of the creation form and the creation itself ask for the same
    data within seconds: this spares the API (and the second request for the head
    office). A failed lookup is not cached. The update of an existing client does not
    use it, it always asks the API.

    Args:
        siret: SIRET number (14 digits).

    Returns:
        The data, or None if the establishment is not found or the API is down.
    """
    key = f"sirene-{siret}"
    data = cache.get(key)
    if data is None:
        data = INSEEApiClient.fetch_by_siret(siret)
        if data is not None:
            cache.set(key, data, SIRENE_CACHE_SECONDS)
    return data


def sync_sirene_status(company: Company, user: "CustomUser") -> None:
    """Store the state, the head office and the NAF 2025 activity reported by Sirene on a new client.

    Called at creation, once the client exists. The data is read again from the SIRET
    (it never comes from the form). Nothing is written when the API cannot be reached.

    Args:
        company: Client just created.
        user: User creating it, recorded as ``updated_by``.
    """
    siret = (company.siret or "").strip()
    if len(siret) != 14 or not siret.isdigit():
        return
    data = get_sirene_data_cached(siret)
    if data is None:
        return
    state, since = get_administrative_state(data)
    values: dict[str, Any] = {
        "headquarters_siret": data.get("headquarters_siret", ""),
        "headquarters_address": data.get("headquarters_address", ""),
        "headquarters_state": data.get("headquarters_state", ""),
        "activity_naf25": data.get("activity_naf25", ""),
        "activity_naf25_label": data.get("activity_naf25_label", ""),
    }
    if state:
        values.update(administrative_state=state, closure_date=since)
    update_tracked_instance(company, user, **values)
