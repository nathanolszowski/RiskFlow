from django.db import models
from core.models import TrackingModel
from django.core.exceptions import ValidationError
from pydantic import ValidationError as PydanticValidationError
from .visit_schema import VisitTemplateSchema
from django.utils import timezone
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
        on_delete=models.PROTECT,
        related_name='inspection_folders',
        verbose_name="Client"
    )

    class Meta(TrackingModel.Meta):
        verbose_name = "Dossier d'inspection"
        verbose_name_plural = "Dossiers d'inspection"
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.reference} - {self.client} {self.current_phase}"
    
    def cascade_archive(self, user=None):
        """
        Propage l'archivage du dossier à toutes ses recommandations liées.
        """
        update_data = {
            'is_active': False,
            'archived_at': timezone.now(),
        }
        if user:
            update_data['archived_by'] = user
            update_data['updated_by'] = user

        self.recommandations.update(**update_data)

"""

==== INSPECTION VISIT SECTION ====

"""

def get_default_template_structure():
    """
    Retourne le squelette JSON par défaut pour un nouveau gabarit de visite.
    """
    return {
        "version": "1.0",
        "sections": [
            {
                "id": "sec_exemple",
                "title": "Nom de la Section (Ex: Sécurité)",
                "order": 1,
                "fields": [
                    {
                        "id": "f_champ_exemple",
                        "label": "Libellé de la question ?",
                        "type": "boolean",
                        "required": True,
                        "order": 1
                    }
                ]
            }
        ]
    }

class VisitTemplate(TrackingModel):
    name = models.CharField(max_length=255, verbose_name="Nom du template")
    description = models.TextField(blank=True, verbose_name="Description")
    shared = models.BooleanField(default=False, verbose_name="Partagé avec tous les utilisateurs")
    schema = models.JSONField(default=get_default_template_structure, verbose_name="Structure du template (JSON)")

    class Meta(TrackingModel.Meta):
        verbose_name = "Modèle de visite"
        verbose_name_plural = "Modèles de visite"

    def clean(self):
        super().clean()
        try:
            VisitTemplateSchema(**self.schema)
        except PydanticValidationError as e:
            raise ValidationError(f"Le format JSON de la structure est invalide : {e}")
        
    def __str__(self):
        return self.name


class VisitInstance(TrackingModel):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Planifiée'
        DELAY = 'DELAY', 'En retard'
        VALIDATED = 'VALIDATED', 'Effectuée'

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
    
    # --- DATA & STATUS ---
    data = models.JSONField(blank=True, default=dict, verbose_name="Données saisies (JSON)")
    current_status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, verbose_name="Statut de la visite")
    due_date = models.DateField(null=True, blank=True, verbose_name="Date de visite")

    class Meta(TrackingModel.Meta):
        verbose_name = "Instance de visite"
        verbose_name_plural = "Instances de visite"
        ordering = ['-created_at']

    def clean(self):
        """
        Automatic population of the template structure if the data field is empty, based on the selected VisitTemplate.
        """
        super().clean()

        if self.template and (not self.data or self.data == {}):

            template_schema = self.template.schema if isinstance(self.template.schema, dict) else {}
            sections = template_schema.get('sections', [])
            
            initial_data = {
                "template_name": self.template.name,
                "sections": []
            }
            
            for section in sections:
                section_data = {
                    "title": section.get("title", ""),
                    "fields": []
                }
                # Pour chaque champ du template, on prépare une clé 'value' vide
                for field in section.get("fields", []):
                    section_data["fields"].append({
                        "label": field.get("label", ""),
                        "type": field.get("type", "text"),
                        "required": field.get("required", False),
                        "value": ""  # 🎯 C'est ici que l'utilisateur écrira sa réponse dans l'admin
                    })
                initial_data["sections"].append(section_data)
            
            # On injecte la structure prête à remplir dans le champ data
            self.data = initial_data

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Visite {self.template.name} - Dossier {self.folder.reference}"

"""

==== INSPECTION RECOMMANDATION SECTION ====

"""

class Recommandation(TrackingModel):
    """
    Model representing a recommendation associated with an inspection folder. Each recommendation has a description, priority, status, and 
    an optional due date. The model also includes relationships to the InspectionFolder model.
    """
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Basse'
        MEDIUM = 'MEDIUM', 'Moyenne'
        HIGH = 'HIGH', 'Haute'
        CRITICAL = 'CRITICAL', 'Critique'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Ouverte'
        IN_PROGRESS = 'IN_PROGRESS', 'En cours'
        RESOLVED = 'RESOLVED', 'Résolue'
        ABANDONED = 'ABANDONED', 'Abandonnée'

    # --- FOLDER RELATIONSHIP ---
    folder = models.ForeignKey(
        InspectionFolder,
        on_delete=models.CASCADE,
        related_name='recommandations',
        verbose_name="Dossier d'inspection"
    )

    # --- DATA ---
    description = models.TextField(verbose_name="Description de la recommandation")
    
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        verbose_name="Priorité"
    )
    
    current_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Statut actuel"
    )
    
    due_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date limite d'exécution"
    )

    class Meta(TrackingModel.Meta):
        verbose_name = "Recommandation"
        verbose_name_plural = "Recommandations"
        ordering = ['due_date', '-priority']

    def __str__(self):
        return f"Rec #{self.folder.reference} - {self.description[:50]} : ({self.current_status})"