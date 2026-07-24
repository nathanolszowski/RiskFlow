from django.db import models
from django.utils import timezone
from core.models import TrackingModel

class Company(TrackingModel):
    reference = models.CharField(max_length=50, unique=True, verbose_name="Référence Société")
    name = models.CharField(max_length=255, verbose_name="Nom de l'entreprise")
    address = models.TextField(verbose_name="Adresse")
    siret = models.CharField(max_length=14, unique=True, verbose_name="Numéro SIRET")
    business_line = models.CharField(max_length=100, verbose_name="Secteur d'activité")
    siren = models.CharField(max_length=9, verbose_name="Numéro SIREN")
    vat_number = models.CharField(max_length=20, verbose_name="Numéro de TVA")
    company_size_category = models.CharField(max_length=100, verbose_name="Catégorie taille de société")
    legal_structure = models.CharField(max_length=100, verbose_name="Structure juridique")
    nb_employees = models.IntegerField(verbose_name="Nombre d'employés")
    creation_date = models.DateField(verbose_name="Date de création")
    labels = models.TextField(verbose_name="Certifications et labels")
    executive_board = models.TextField(verbose_name="Conseil d'administration")
    website = models.URLField(verbose_name="Site web")

    class Meta(TrackingModel.Meta):
        verbose_name = "Société"
        verbose_name_plural = "Sociétés"
        ordering = ['name']

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
            # Auto-generate the reference if it's not provided
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
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='contacts', verbose_name="Société")
    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    email = models.EmailField(verbose_name="Email")
    phone_number_fix = models.CharField(max_length=20, verbose_name="Numéro de téléphone fixe")
    phone_number_mobile = models.CharField(max_length=20, verbose_name="Numéro de téléphone mobile")
    position = models.CharField(max_length=100, verbose_name="Poste")

    class Meta(TrackingModel.Meta):
        verbose_name = "Contact"
        verbose_name_plural = "Contacts"
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.company.name}"