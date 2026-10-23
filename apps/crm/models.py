"""Models of the crm app: companies (clients) and their contacts."""

from typing import TYPE_CHECKING, Any, Optional

from core.models import AddressMixin, TrackingModel
from django.db import models
from django.utils import timezone

from .services.legal_forms import legal_form_label

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models.fields.related_descriptors import RelatedManager


class Company(TrackingModel, AddressMixin):
    """Client company inspected by the user.

    Archiving a company archives its active contacts (see ``cascade_archive``).
    A company with inspection folders, even archived ones, cannot be deleted.

    Attributes:
        reference: Unique reference, generated as ``SOC-<year>-<number>`` when empty.
        name: Company name.
        address_line, postal_code, city: Postal address (see ``AddressMixin``).
        siret: Unique SIRET number (14 digits).
        siren: SIREN number (9 digits).
        vat_number: Optional VAT number.
        business_line: Business sector.
        company_size_category: Size category (SME, ETI, large company...).
        legal_structure: Optional legal structure.
        nb_employees: Optional number of employees (None when unknown).
        administrative_state: Administrative state reported by Sirene at the last
            import or update (empty when never checked), see ``SireneState``.
        closure_date: Closing date of the establishment, when Sirene reports it closed.
        activity_naf25: Main activity code (NAF 2025), from Sirene.
        activity_naf25_label: Label of that activity, read from the INSEE nomenclature.
        headquarters_siret: SIRET of the head office (same as ``siret`` when the
            establishment is the head office), from Sirene.
        headquarters_address: Address of the head office, from Sirene.
        headquarters_state: Administrative state of the head office (``A`` or ``F``).
        creation_date: Date the company was created.
        labels: Optional certifications and labels.
        executive_board: Optional board of directors.
        website: Optional website.
        contacts: Reverse relation to the company's contacts.
        inspection_folders: Reverse relation to the company's inspection folders.
    """

    class SireneState(models.TextChoices):
        """Administrative state reported by the Sirene API (informative only)."""

        ACTIVE = "A", "Actif"
        CLOSED = "F", "Établissement fermé"
        CEASED = "C", "Entreprise cessée"

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence client"
    )
    name = models.CharField(max_length=255, verbose_name="Nom du client")
    siret = models.CharField(max_length=14, unique=True, verbose_name="Numéro SIRET")
    business_line = models.CharField(max_length=100, verbose_name="Secteur d'activité")
    siren = models.CharField(max_length=9, verbose_name="Numéro SIREN")
    vat_number = models.CharField(
        max_length=20, blank=True, verbose_name="Numéro de TVA"
    )
    company_size_category = models.CharField(
        max_length=100, verbose_name="Catégorie de taille du client"
    )
    legal_structure = models.CharField(
        max_length=100, blank=True, verbose_name="Structure juridique"
    )
    nb_employees = models.IntegerField(
        null=True, blank=True, verbose_name="Nombre d'employés"
    )
    creation_date = models.DateField(verbose_name="Date de création")
    labels = models.TextField(blank=True, verbose_name="Certifications et labels")
    executive_board = models.TextField(
        blank=True, verbose_name="Conseil d'administration"
    )
    website = models.URLField(blank=True, verbose_name="Site web")
    administrative_state = models.CharField(
        max_length=1,
        choices=SireneState.choices,
        blank=True,
        verbose_name="État administratif (Sirene)",
    )
    closure_date = models.DateField(
        null=True, blank=True, verbose_name="Date de fermeture"
    )
    activity_naf25 = models.CharField(
        max_length=10, blank=True, verbose_name="Activité principale (NAF 2025)"
    )
    activity_naf25_label = models.CharField(
        max_length=255, blank=True, verbose_name="Libellé de l'activité (NAF 2025)"
    )
    headquarters_siret = models.CharField(
        max_length=14, blank=True, verbose_name="SIRET du siège social"
    )
    headquarters_address = models.TextField(
        blank=True, verbose_name="Adresse du siège social"
    )
    headquarters_state = models.CharField(
        max_length=1,
        choices=SireneState.choices,
        blank=True,
        verbose_name="État du siège social",
    )

    if TYPE_CHECKING:
        # Reverse relation (related_name), declared for Pylance only
        contacts: "RelatedManager[Contact]"
        # Untyped on purpose: crm must not import inspections (inspections depends on crm, never the reverse)
        inspection_folders: "RelatedManager[Any]"

    class Meta(TrackingModel.Meta):
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["name"]

    def __str__(self) -> str:
        """Return the company name."""
        return f"{self.name}"

    def cascade_archive(self, user: Optional["CustomUser"] = None) -> None:
        """Archive the active contacts with the company's archive date.

        Contacts still referenced by an active folder are skipped, like a direct
        contact archive would be refused. Unarchiving a company intentionally
        leaves its contacts archived.

        Args:
            user: User performing the action, recorded as ``archived_by`` and
                ``updated_by`` of the contacts.
        """
        update_data = {
            "is_active": False,
            # Same date as the company, to tell these contacts apart from ones archived separately
            "archived_at": self.archived_at or timezone.now(),
        }
        if user:
            update_data["archived_by"] = user
            update_data["updated_by"] = user

        self.contacts.filter(is_active=True).exclude(
            inspection_folders__is_active=True
        ).update(**update_data)

    @property
    def legal_structure_display(self) -> str:
        """Return the legal form with its label when the stored value is an INSEE code.

        Sirene gives a code (``5499``): it is shown as its label. A value typed by hand
        (``SAS``) is shown as it is.
        """
        return legal_form_label(self.legal_structure)

    @property
    def activity_naf25_display(self) -> str:
        """Return the main activity as ``label (code)``, or the code alone if the label is unknown."""
        if self.activity_naf25 and self.activity_naf25_label:
            return f"{self.activity_naf25_label} ({self.activity_naf25})"
        return self.activity_naf25

    @property
    def is_headquarters(self) -> bool:
        """Return True if this establishment is the head office of the company."""
        return bool(self.headquarters_siret) and self.headquarters_siret == self.siret

    @property
    def headquarters_company(self) -> Optional["Company"]:
        """Return the client whose SIRET is the head office, if it is another one."""
        if not self.headquarters_siret or self.is_headquarters:
            return None
        return Company.objects.filter(siret=self.headquarters_siret).first()

    @property
    def cessation_alert(self) -> Optional[dict[str, Any]]:
        """Return the cessation alert to show, from the state stored at the last Sirene check.

        Returns:
            None unless the company is reported closed or ceased, otherwise a dict
            with ``kind`` (``"ceased"`` or ``"closed"``), ``since`` (date or None) and
            the state and address of the head office (``hq_state``, ``hq_address``).
        """
        hq = {
            "hq_state": self.headquarters_state,
            "hq_address": self.headquarters_address,
        }
        if self.administrative_state == self.SireneState.CEASED:
            return {"kind": "ceased", "since": None, **hq}
        if self.administrative_state == self.SireneState.CLOSED:
            return {"kind": "closed", "since": self.closure_date, **hq}
        return None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the company, generating its reference when empty.

        The reference is ``SOC-<year>-<number>``: the number follows the last
        reference of the year, on four digits.

        Args:
            *args: Positional arguments passed to ``Model.save()``.
            **kwargs: Keyword arguments passed to ``Model.save()``.
        """
        if not self.reference:
            current_year = timezone.now().year
            prefix = f"SOC-{current_year}-"
            last_company = (
                Company.objects.filter(reference__startswith=prefix)
                .order_by("-id")
                .first()
            )
            if last_company and last_company.reference:
                try:
                    last_number = int(last_company.reference.split("-")[-1])
                    new_number = last_number + 1
                except ValueError:
                    new_number = 1
            else:
                new_number = 1

            self.reference = f"{prefix}{new_number:04d}"

        super().save(*args, **kwargs)


class Contact(TrackingModel):
    """Person to contact in a company.

    A contact referenced by an inspection folder, even archived, can be neither
    deleted nor archived while the folder is active.

    Attributes:
        company: Company the contact belongs to.
        first_name: First name.
        last_name: Last name.
        email: Optional email address.
        phone_number_fix: Optional landline number.
        phone_number_mobile: Optional mobile number.
        position: Job title.
        inspection_folders: Reverse relation to the folders referencing the contact.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name="Client",
    )
    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    email = models.EmailField(max_length=60, blank=True, verbose_name="Email")
    phone_number_fix = models.CharField(
        max_length=20, blank=True, verbose_name="Numéro de téléphone fixe"
    )
    phone_number_mobile = models.CharField(
        max_length=20, blank=True, verbose_name="Numéro de téléphone mobile"
    )
    position = models.CharField(max_length=100, verbose_name="Poste")

    if TYPE_CHECKING:
        # Reverse relation (related_name), declared for Pylance only
        # Untyped on purpose: crm must not import inspections (inspections depends on crm, never the reverse)
        inspection_folders: "RelatedManager[Any]"

    class Meta(TrackingModel.Meta):
        verbose_name = "Contact"
        verbose_name_plural = "Contacts"
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        """Return the full name followed by the company name."""
        return f"{self.first_name} {self.last_name} - {self.company.name}"
