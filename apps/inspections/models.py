from django.db import models
from core.models import TrackingModel
from django.core.exceptions import ValidationError
import copy
from .validators import (
    get_default_template_structure,
    validate_template_schema,
    validate_answers,
    AnswersValidationError,
    compute_progress,
)
from django.utils import timezone
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager
"""

==== INSPECTION FOLDER SECTION ====

"""

class InspectionFolder(TrackingModel):
    class Phase(models.TextChoices):
        CREATION = 'CREATION', 'Création'
        PREPARATION = 'PREPARATION', 'Préparation'
        VISIT = 'VISIT', 'Visite'
        REPORT = 'REPORT', 'Rapport'
        FOLLOW_UP = 'FOLLOW_UP', 'Suivi'
        CLOSED = 'CLOSED', 'Clôturé'
        ARCHIVED = 'ARCHIVED', 'Archivé'

    # Ordered phases displayed in the progress bar (ARCHIVED is out of the progression)
    PROGRESS_PHASES = [
        Phase.CREATION, Phase.PREPARATION, Phase.VISIT, Phase.REPORT, Phase.FOLLOW_UP, Phase.CLOSED,
    ]

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

    if TYPE_CHECKING:
        # Reverse relations (related_name), declared for Pylance only
        visits: 'RelatedManager[VisitInstance]'
        recommandations: 'RelatedManager[Recommandation]'

    class Meta(TrackingModel.Meta):
        verbose_name = "Dossier d'inspection"
        verbose_name_plural = "Dossiers d'inspection"
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.reference} - {self.company} {self.current_phase}"
    
    def cascade_archive(self, user=None):
        """
        Properly archive the inspection folder and all its associated visits and recommendations. This method sets the `is_active` field to False and records the current timestamp in the `archived_at` field for the folder and its children. If a user is provided, it also records who performed the archiving action.
        """
        update_data = {
            'is_active': False,
            # Same date as the folder, so that cascade_unarchive can restore only these visits and recommendations
            'archived_at': self.archived_at or timezone.now(),
        }
        if user:
            update_data['archived_by'] = user
            update_data['updated_by'] = user

        self.visits.filter(is_active=True).update(**update_data)
        self.recommandations.filter(is_active=True).update(**update_data)

    def cascade_unarchive(self, archived_at=None, user=None):
        """
        Restore the visits and recommendations archived together with the inspection folder (same archive date). Items archived
        on their own beforehand stay archived.
        """
        if not archived_at:
            return

        update_data = {
            'is_active': True,
            'archived_at': None,
            'archived_by': None,
        }
        if user:
            update_data['updated_by'] = user

        self.visits.filter(is_active=False, archived_at=archived_at).update(**update_data)
        self.recommandations.filter(is_active=False, archived_at=archived_at).update(**update_data)

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
        
        # First upcoming visit with a due date greater than or equal to today
        next_visit = self.visits.filter(
            due_date__gte=timezone.now()
        ).order_by('due_date').first()
        
        return next_visit.due_date if next_visit else None

    @property
    def phase_progress(self):
        """
        Return the progress of the folder through its phases for the progress bar, or None if the folder is archived.
        """
        if self.current_phase not in self.PROGRESS_PHASES:
            return None

        current_index = self.PROGRESS_PHASES.index(self.current_phase)
        last_index = len(self.PROGRESS_PHASES) - 1
        steps = []
        for index, phase in enumerate(self.PROGRESS_PHASES):
            if index < current_index:
                state = "done"
            elif index == current_index:
                state = "current"
            else:
                state = "todo"
            steps.append({
                "label": phase.label,
                "state": state,
                "style": f"left: {round(index / last_index * 100)}%",
            })

        return {
            "style": f"width: {round(current_index / last_index * 100)}%",
            "steps": steps,
        }

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
        validate_template_schema(self.schema)

    def save(self, *args, **kwargs):
        # Skipped when only some fields are written (e.g. archive metadata), as the schema is then untouched
        if kwargs.get("update_fields") is None:
            self.full_clean()
        super().save(*args, **kwargs)

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
    # The template is only the origin of the visit: the visit works on its own snapshot (instance_schema),
    # so the template can be edited, archived or deleted without any effect on the visit.
    template = models.ForeignKey(
        VisitTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instances',
        verbose_name="Template d'origine"
    )
    template_name = models.CharField(max_length=255, blank=True, verbose_name="Nom du template d'origine")
    instance_schema = models.JSONField(blank=True, default=dict, verbose_name="Structure de l'instance (JSON)")
    
    # --- DATA & STATUS ---
    # Answers are stored as {"answers": {"<field id>": value}}, keyed by the ids of instance_schema
    data = models.JSONField(blank=True, default=dict, verbose_name="Données saisies (JSON)")
    revision = models.PositiveIntegerField(default=0, verbose_name="Révision des réponses")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin de la visite")
    current_status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, verbose_name="Statut de la visite")
    due_date = models.DateField(null=True, blank=True, verbose_name="Date de visite")
    notes = models.TextField(
        blank=True,
        verbose_name="Notes sur la visite"
    )

    if TYPE_CHECKING:
        # FK id attribute, declared for Pylance only
        folder_id: int

    class Meta(TrackingModel.Meta):
        verbose_name = "Instance de visite"
        verbose_name_plural = "Instances de visite"
        ordering = ['-created_at']

    def snapshot_template(self):
        """Freeze the structure of the template into the visit."""
        if self.template:
            self.instance_schema = copy.deepcopy(self.template.schema)
            self.template_name = self.template.name

    def clean(self):
        """
        Snapshot of the template if the visit has no structure yet, then validation of the structure
        and of the answers against it (required fields are only enforced once the visit is done).
        """
        super().clean()

        if not self.instance_schema:
            self.snapshot_template()
        validate_template_schema(self.instance_schema)

        if not isinstance(self.data, dict):
            raise ValidationError("Les données de la visite doivent être un objet JSON.")
        answers = self.data.get("answers", {})
        # Required fields are only enforced by the "Terminer" action of the form (complete_visit):
        # a visit can also be ticked as done from its planning, e.g. when it was filled elsewhere.
        try:
            cleaned = validate_answers(self.instance_schema, answers)
        except AnswersValidationError as e:
            # A plain error: the keys of the field errors are field ids of the visit, not fields of a form
            raise ValidationError("Réponses invalides : " + " ; ".join(e.field_errors.values()))
        self.data = {**self.data, "answers": cleaned}

    def save(self, *args, **kwargs):
        # Skipped when only some fields are written: the answers are validated by the service that writes them
        if kwargs.get("update_fields") is None:
            self.full_clean()
        super().save(*args, **kwargs)

    @property
    def answers(self):
        return self.data.get("answers", {}) if isinstance(self.data, dict) else {}

    @property
    def progress(self):
        return compute_progress(self.instance_schema, self.answers)

    @property
    def is_late(self):
        """A planned visit whose date is over (the stored DELAY status is kept for the existing records)."""
        if self.current_status == self.Status.DELAY:
            return True
        return (
            self.current_status == self.Status.SCHEDULED
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )

    @property
    def days_until_due(self):
        """Days left before the visit date (negative when over), or None without date."""
        if not self.due_date:
            return None
        return (self.due_date - timezone.localdate()).days

    @property
    def display_template_name(self):
        return self.template_name or (self.template.name if self.template else "Template supprimé")

    @property
    def template_is_available(self):
        return self.template is not None and self.template.is_active

    def __str__(self):
        return f"Visite {self.display_template_name} - Dossier {self.folder.reference}"

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

    if TYPE_CHECKING:
        # FK id attribute, declared for Pylance only
        folder_id: int

    class Meta(TrackingModel.Meta):
        verbose_name = "Recommandation"
        verbose_name_plural = "Recommandations"
        ordering = ['due_date', '-priority']

    @property
    def days_until_due(self):
        """
        Days left before the due date (negative when overdue), or None without due date.
        """
        if not self.due_date:
            return None
        return (self.due_date - timezone.localdate()).days

    def __str__(self):
        return f"Rec #{self.folder.reference} - {self.description[:50]} : ({self.current_status})"