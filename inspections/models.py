from django.db import models
from core.models import TrackingModel
from django.core.exceptions import ValidationError
from pydantic import ValidationError as PydanticValidationError
from .validators import VisitTemplateSchema, get_default_template_structure
from django.utils import timezone
import uuid
"""

==== INSPECTION FOLDER SECTION ====

"""

class InspectionFolder(TrackingModel):
    class Phase(models.TextChoices):
        CREATION = 'CREATION', 'En création'
        IN_PROGRESS = 'IN_PROGRESS', 'Dossier en cours'
        REVIEW = 'REVIEW', 'En cours de revue'
        COMPLETED = 'COMPLETED', 'Terminé / Clôturé'
        ARCHIVED = 'ARCHIVED', 'Archivé'

    reference = models.CharField(max_length=100, unique=True, verbose_name="Référence du dossier")
    current_phase = models.CharField(max_length=20, choices=Phase.choices, default=Phase.CREATION, verbose_name="Phase actuelle")
    notes = models.TextField(blank=True, verbose_name="Notes internes")
    inspection_site_address = models.TextField(blank=True, verbose_name="Adresse du site d'inspection")

    # --- COMPANY RELATIONSHIP ---
    company = models.ForeignKey(
        'crm.Company',
        on_delete=models.PROTECT,
        related_name='inspection_folders',
        verbose_name="Société"
    )
    # --- CONTACT RELATIONSHIP ---
    contact = models.ForeignKey(
        'crm.Contact',
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='inspection_folders',
        verbose_name="Contact référent"
    )

    class Meta(TrackingModel.Meta):
        verbose_name = "Dossier d'inspection"
        verbose_name_plural = "Dossiers d'inspection"
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.reference} - {self.company} {self.current_phase}"
    
    def cascade_archive(self, user=None):
        """
        Properly archive the inspection folder and all its associated recommendations. This method sets the `is_active` field to False and records the current timestamp in the `archived_at` field for both the folder and its recommendations. If a user is provided, it also records who performed the archiving action.
        """
        update_data = {
            'is_active': False,
            'archived_at': timezone.now(),
        }
        if user:
            update_data['archived_by'] = user
            update_data['updated_by'] = user

        self.recommandations.update(**update_data)

    def generate_unique_reference(self):
        """
        Génère un format métier type DOS-ANNEE-HEXALÉATOIRE (ex: DOS-2026-A8F3B2).
        Garantit l'unicité via une boucle de vérification.
        """
        year = timezone.now().year
        while True:
            # Code aléatoire de 6 caractères hexadécimaux
            random_code = uuid.uuid4().hex[:6].upper()
            ref = f"DOS-{year}-{random_code}"
            
            # On vérifie si la référence existe déjà en BDD
            if not InspectionFolder.objects.filter(reference=ref).exists():
                return ref
            
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_unique_reference()
        super().save(*args, **kwargs)

    @property
    def count_all_recommandations(self):
        """
        Return the total number of recommendation instances associated with this inspection folder.
        """
        return self.recommandations.count()
    
    @property
    def count_all_visits(self):
        """
        Return the total number of visit instances associated with this inspection folder.
        """
        return self.visits.count()
    
    @property
    def get_latest_visit(self):
        """
        Return the latest visit instance associated with this inspection folder, ordered by creation date in descending order.
        """
        return self.visits.order_by('-created_at').first()
    
    @property
    def next_visit_date(self):
        """Return the date of the next scheduled visit for this inspection folder, or None if there are no upcoming visits."""
        from django.utils import timezone
        
        # On cherche la première visite dont la date est supérieure ou égale à aujourd'hui
        next_visit = self.visits.filter(
            due_date__gte=timezone.now()
        ).order_by('due_date').first()
        
        return next_visit.due_date if next_visit else None

"""

==== INSPECTION VISIT SECTION ====

"""

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
    instance_schema = models.JSONField(blank=True, default=dict, verbose_name="Structure de l'instance (JSON)")
    
    # --- DATA & STATUS ---
    data = models.JSONField(blank=True, default=dict, verbose_name="Données saisies (JSON)")
    current_status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, verbose_name="Statut de la visite")
    due_date = models.DateField(null=True, blank=True, verbose_name="Date de visite")
    notes = models.TextField(
        blank=True,
        verbose_name="Notes sur la visite"
    )

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
                for field in section.get("fields", []):
                    section_data["fields"].append({
                        "label": field.get("label", ""),
                        "type": field.get("type", "text"),
                        "required": field.get("required", False),
                        "value": ""
                    })
                initial_data["sections"].append(section_data)
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
    topic = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Sujet de la recommandation"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Notes sur la recommandation"
    )

    class Meta(TrackingModel.Meta):
        verbose_name = "Recommandation"
        verbose_name_plural = "Recommandations"
        ordering = ['due_date', '-priority']

    def __str__(self):
        return f"Rec #{self.folder.reference} - {self.description[:50]} : ({self.current_status})"