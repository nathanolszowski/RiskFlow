from django.db import models
from django.conf import settings
from core.models import TrackingModel
from django.core.exceptions import ValidationError

"""

==== INSPECTION FOLDER SECTION ====

"""

class InspectionFolder(TrackingModel):
    class Phase(models.TextChoices):
        CREATION = 'CREATION', 'En création'
        ASSIGNED = 'ASSIGNED', 'Assigné / Planifié'
        IN_PROGRESS = 'IN_PROGRESS', 'Dossier en cours'
        REVIEW = 'REVIEW', 'En cours de revue'
        COMPLETED = 'COMPLETED', 'Terminé / Clôturé'
        ARCHIVED = 'ARCHIVED', 'Archivé'

    reference = models.CharField(max_length=100, unique=True, verbose_name="Référence du dossier")
    current_phase = models.CharField(max_length=20, choices=Phase.choices, default=Phase.CREATION, verbose_name="Phase actuelle")

    # --- CLIENT RELATIONSHIP ---
    client = models.ForeignKey(
        'clients.Clients',
        on_delete=models.PROTECT, # Protect the client if there are inspection folders associated with it
        related_name='inspection_folders', # Can access to all inspection folders of a client via client.inspection_folders.all()
        verbose_name="Client"
    )

    class Meta(TrackingModel.Meta):
        verbose_name = "Dossier d'inspection"
        verbose_name_plural = "Dossiers d'inspection"
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.reference} - {self.client} {self.current_phase}"

"""

==== INSPECTION VISIT SECTION ====

"""

class VisitTemplate(TrackingModel):
    name = models.CharField(max_length=255, verbose_name="Nom du template")
    description = models.TextField(blank=True, verbose_name="Description")
    
    # Stocke la structure dynamique du formulaire (champs, types, etc.)
    schema = models.JSONField(verbose_name="Schéma du formulaire (JSON)")

    class Meta(TrackingModel.Meta):
        verbose_name = "Modèle de visite"
        verbose_name_plural = "Modèles de visite"

    def __str__(self):
        return self.name


class VisitInstance(TrackingModel):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Planifiée'
        IN_PROGRESS = 'IN_PROGRESS', 'En cours'
        SUBMITTED = 'SUBMITTED', 'Soumise / À valider'
        VALIDATED = 'VALIDATED', 'Validée'

    # --- INSPECTION FOLDER RELATIONSHIP ---
    folder = models.ForeignKey(
        'InspectionFolder', 
        on_delete=models.CASCADE, 
        related_name='visits', 
        verbose_name="Dossier associé"
    )
    template = models.ForeignKey(
        VisitTemplate, 
        on_delete=models.PROTECT, 
        related_name='instances', 
        verbose_name="Template utilisé"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name='assigned_visits', 
        verbose_name="Inspecteur terrain"
    )
    
    # --- DATA & STATUS ---
    data = models.JSONField(blank=True, default=dict, verbose_name="Données saisies (JSON)")
    current_status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, verbose_name="Statut de la visite")

    class Meta(TrackingModel.Meta):
        verbose_name = "Instance de visite"
        verbose_name_plural = "Instances de visite"
        ordering = ['-created_at']

    def clean(self):
        """
        Only the inspection folder's owner can create a VisitInstance for that folder.
        """
        super().clean()
        
        # Check if the folder is set and if this is a new instance (not yet saved)
        if self.folder and not self.pk:
            # self.created_by is the user who is creating the VisitInstance, we check if they are the same as the folder's created_by
            if self.folder.created_by != self.created_by:
                raise ValidationError({
                    'folder': "Sécurité : Vous ne pouvez pas créer de visite pour ce dossier car vous n'en êtes pas le propriétaire."
                })

    def save(self, *args, **kwargs):
        # Clean force the instance before saving to enforce validation rules
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Visite {self.template.name} - Dossier {self.folder.reference}"