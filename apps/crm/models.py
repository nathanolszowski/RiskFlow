"""Models of the crm app: companies (clients) and their contacts."""

from typing import TYPE_CHECKING, Any, Optional

from core.models import TrackingModel
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models.fields.related_descriptors import RelatedManager
    from inspections.models import InspectionFolder


class Company(TrackingModel):
    """Client company inspected by the user.

    Archiving a company archives its active contacts (see ``cascade_archive``).
    A company with inspection folders, even archived ones, cannot be deleted.

    Attributes:
        reference: Unique reference, generated as ``SOC-<year>-<number>`` when empty.
        name: Company name.
        address: Postal address.
        siret: Unique SIRET number (14 digits).
        siren: SIREN number (9 digits).
        vat_number: Optional VAT number.
        business_line: Business sector.
        company_size_category: Size category (SME, ETI, large company...).
        legal_structure: Optional legal structure.
        nb_employees: Number of employees.
        creation_date: Date the company was created.
        labels: Optional certifications and labels.
        executive_board: Optional board of directors.
        website: Optional website.
        contacts: Reverse relation to the company's contacts.
        inspection_folders: Reverse relation to the company's inspection folders.
    """

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence Société"
    )
    name = models.CharField(max_length=255, verbose_name="Nom de l'entreprise")
    address = models.TextField(verbose_name="Adresse")
    siret = models.CharField(max_length=14, unique=True, verbose_name="Numéro SIRET")
    business_line = models.CharField(max_length=100, verbose_name="Secteur d'activité")
    siren = models.CharField(max_length=9, verbose_name="Numéro SIREN")
    vat_number = models.CharField(
        max_length=20, blank=True, verbose_name="Numéro de TVA"
    )
    company_size_category = models.CharField(
        max_length=100, verbose_name="Catégorie taille de société"
    )
    legal_structure = models.CharField(
        max_length=100, blank=True, verbose_name="Structure juridique"
    )
    nb_employees = models.IntegerField(blank=True, verbose_name="Nombre d'employés")
    creation_date = models.DateField(verbose_name="Date de création")
    labels = models.TextField(blank=True, verbose_name="Certifications et labels")
    executive_board = models.TextField(
        blank=True, verbose_name="Conseil d'administration"
    )
    website = models.URLField(blank=True, verbose_name="Site web")

    if TYPE_CHECKING:
        # Reverse relation (related_name), declared for Pylance only
        contacts: "RelatedManager[Contact]"
        inspection_folders: "RelatedManager[InspectionFolder]"

    class Meta(TrackingModel.Meta):
        verbose_name = "Société"
        verbose_name_plural = "Sociétés"
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
        verbose_name="Société",
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
        inspection_folders: "RelatedManager[InspectionFolder]"

    class Meta(TrackingModel.Meta):
        verbose_name = "Contact"
        verbose_name_plural = "Contacts"
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        """Return the full name followed by the company name."""
        return f"{self.first_name} {self.last_name} - {self.company.name}"
