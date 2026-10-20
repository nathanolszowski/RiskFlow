"""Models of the inspections app: folders, visit templates, visits and recommendations."""

import copy
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from core.models import TrackingModel
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .validators import (
    AnswersValidationError,
    compute_progress,
    get_default_template_structure,
    validate_answers,
    validate_template_schema,
)

if TYPE_CHECKING:
    from accounts.models import CustomUser
    from django.db.models.fields.related_descriptors import RelatedManager
    from medias.models import Media
"""

==== INSPECTION FOLDER SECTION ====

"""


class InspectionFolder(TrackingModel):
    """Inspection folder: the mission of an inspector for a company.

    A folder goes through the phases of ``Phase`` (creation, preparation, visit,
    report, follow-up, closed). It owns its visits and recommendations: archiving
    it archives them with the same date, and deleting it deletes them.

    Attributes:
        reference: Unique reference, generated as ``DOS-<year>-<6 hex>`` when empty.
        current_phase: Current phase of the mission.
        notes: Internal notes.
        inspection_site_address: Address of the inspected site.
        company: Inspected company (cannot be deleted while it has folders).
        contact: Optional referent contact.
        visits: Reverse relation to the visits of the folder.
        recommandations: Reverse relation to the recommendations of the folder.
        PROGRESS_PHASES: Ordered phases shown in the progress bar.
    """

    class Phase(models.TextChoices):
        CREATION = "CREATION", "Création"
        PREPARATION = "PREPARATION", "Préparation"
        VISIT = "VISIT", "Visite"
        REPORT = "REPORT", "Rapport"
        FOLLOW_UP = "FOLLOW_UP", "Suivi"
        CLOSED = "CLOSED", "Clôturé"
        ARCHIVED = "ARCHIVED", "Archivé"

    # Ordered phases displayed in the progress bar (ARCHIVED is out of the progression)
    PROGRESS_PHASES = [
        Phase.CREATION,
        Phase.PREPARATION,
        Phase.VISIT,
        Phase.REPORT,
        Phase.FOLLOW_UP,
        Phase.CLOSED,
    ]

    reference = models.CharField(
        max_length=100, unique=True, verbose_name="Référence du dossier"
    )
    current_phase = models.CharField(
        max_length=20,
        choices=Phase.choices,
        default=Phase.CREATION,
        verbose_name="Phase actuelle",
    )
    notes = models.TextField(blank=True, verbose_name="Notes internes")
    inspection_site_address = models.TextField(
        blank=True, verbose_name="Adresse du site d'inspection"
    )

    # --- COMPANY RELATIONSHIP ---
    company = models.ForeignKey(
        "crm.Company",
        on_delete=models.PROTECT,
        related_name="inspection_folders",
        verbose_name="Société",
    )
    # --- CONTACT RELATIONSHIP ---
    contact = models.ForeignKey(
        "crm.Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspection_folders",
        verbose_name="Contact référent",
    )

    if TYPE_CHECKING:
        # Reverse relations (related_name), declared for Pylance only
        visits: "RelatedManager[VisitInstance]"
        recommandations: "RelatedManager[Recommandation]"
        medias: "RelatedManager[Media]"

    class Meta(TrackingModel.Meta):
        verbose_name = "Dossier d'inspection"
        verbose_name_plural = "Dossiers d'inspection"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        """Return the reference, the company and the current phase."""
        return f"{self.reference} - {self.company} {self.current_phase}"

    def cascade_archive(self, user: Optional["CustomUser"] = None) -> None:
        """Archive the active visits, recommendations and medias of the folder.

        They receive the same ``archived_at`` as the folder, so that
        ``cascade_unarchive()`` can restore only these ones.

        Args:
            user: User performing the action, recorded as ``archived_by`` and
                ``updated_by`` of the children.
        """
        update_data = {
            "is_active": False,
            # Same date as the folder, so that cascade_unarchive can restore only these visits and recommendations
            "archived_at": self.archived_at or timezone.now(),
        }
        if user:
            update_data["archived_by"] = user
            update_data["updated_by"] = user

        self.visits.filter(is_active=True).update(**update_data)
        self.recommandations.filter(is_active=True).update(**update_data)
        self.medias.filter(is_active=True).update(**update_data)

    def cascade_unarchive(
        self,
        archived_at: Optional[datetime] = None,
        user: Optional["CustomUser"] = None,
    ) -> None:
        """Restore the visits, recommendations and medias archived together with the folder.

        Items archived on their own beforehand (different archive date) stay
        archived.

        Args:
            archived_at: Archive date of the folder before it was unarchived. Nothing
                is restored without it.
            user: User performing the action, recorded as ``updated_by``.
        """
        if not archived_at:
            return

        update_data = {
            "is_active": True,
            "archived_at": None,
            "archived_by": None,
        }
        if user:
            update_data["updated_by"] = user

        self.visits.filter(is_active=False, archived_at=archived_at).update(
            **update_data
        )
        self.recommandations.filter(is_active=False, archived_at=archived_at).update(
            **update_data
        )
        self.medias.filter(is_active=False, archived_at=archived_at).update(
            **update_data
        )

    def generate_unique_reference(self) -> str:
        """Generate a reference such as ``DOS-2026-A8F3B2``.

        The year is followed by six random hexadecimal characters. Uniqueness is
        guaranteed by checking the database in a loop.

        Returns:
            A reference not used by any folder yet.
        """
        year = timezone.now().year
        while True:
            # Code aléatoire de 6 caractères hexadécimaux
            random_code = uuid.uuid4().hex[:6].upper()
            ref = f"DOS-{year}-{random_code}"

            # On vérifie si la référence existe déjà en BDD
            if not InspectionFolder.objects.filter(reference=ref).exists():
                return ref

    def clean(self) -> None:
        """Check that the referent contact belongs to the company of the folder.

        Raises:
            ValidationError: If the contact belongs to another company.
        """
        super().clean()
        if (
            self.contact_id
            and self.company_id
            and self.contact.company_id != self.company_id
        ):
            raise ValidationError(
                {"contact": "Ce contact n'appartient pas à la société du dossier."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the folder, generating its reference when empty.

        ``clean()`` is not called by Django on ``save()``: it is run here whenever the
        company or the contact can change (not for ``update_fields`` writes such as
        archiving).

        Args:
            *args: Positional arguments passed to ``Model.save()``.
            **kwargs: Keyword arguments passed to ``Model.save()``.

        Raises:
            ValidationError: If the contact does not belong to the company.
        """
        update_fields = kwargs.get("update_fields")
        if update_fields is None or {
            "company",
            "company_id",
            "contact",
            "contact_id",
        } & set(update_fields):
            self.clean()
        if not self.reference:
            self.reference = self.generate_unique_reference()
        super().save(*args, **kwargs)

    @property
    def count_all_recommandations(self) -> int:
        """Return the total number of recommendations of the folder, archived ones included."""
        return self.recommandations.count()

    @property
    def count_all_visits(self) -> int:
        """Return the total number of visits of the folder, archived ones included."""
        return self.visits.count()

    @property
    def get_latest_visit(self) -> Optional["VisitInstance"]:
        """Return the most recently created visit of the folder, or None if it has none."""
        return self.visits.order_by("-created_at").first()

    @property
    def next_visit_date(self) -> Optional[date]:
        """Return the date of the next scheduled visit of the folder.

        Returns:
            The earliest due date from today on, or None if there is no upcoming visit.
        """
        from django.utils import timezone

        # First upcoming visit with a due date greater than or equal to today
        next_visit = (
            self.visits.filter(due_date__gte=timezone.now())
            .order_by("due_date")
            .first()
        )

        return next_visit.due_date if next_visit else None

    @property
    def phase_progress(self) -> Optional[dict[str, Any]]:
        """Return the progress of the folder through its phases, for the progress bar.

        Returns:
            A dict with the ``style`` of the filled bar and the ``steps``, each with
            its ``label``, ``state`` (``done``, ``current`` or ``todo``) and
            ``style``. None if the phase is not part of the progression (archived).
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
            steps.append(
                {
                    "label": phase.label,
                    "state": state,
                    "style": f"left: {round(index / last_index * 100)}%",
                }
            )

        return {
            "style": f"width: {round(current_index / last_index * 100)}%",
            "steps": steps,
        }


"""

==== INSPECTION VISIT SECTION ====

"""


class VisitTemplate(TrackingModel):
    """Template describing a visit form in JSON.

    A visit takes a snapshot of the template when it is created, so editing,
    archiving or deleting a template never changes existing visits. Only its owner
    can edit it, a shared template can be consulted and copied.

    Attributes:
        name: Name of the template.
        description: Optional description.
        shared: Whether all users can use the template.
        schema: Structure of the form, validated by ``VisitTemplateSchema``.
        instances: Reverse relation to the visits created from the template.
    """

    name = models.CharField(max_length=255, verbose_name="Nom du template")
    description = models.TextField(blank=True, verbose_name="Description")
    shared = models.BooleanField(
        default=False, verbose_name="Partagé avec tous les utilisateurs"
    )
    schema = models.JSONField(
        default=get_default_template_structure,
        verbose_name="Structure du template (JSON)",
    )

    class Meta(TrackingModel.Meta):
        verbose_name = "Modèle de visite"
        verbose_name_plural = "Modèles de visite"

    def clean(self) -> None:
        """Validate the structure of the template.

        Raises:
            django.core.exceptions.ValidationError: If the schema is invalid.
        """
        super().clean()
        validate_template_schema(self.schema)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the template, validating it first with ``full_clean()``.

        The validation is skipped when only some fields are written
        (``update_fields``, e.g. archive metadata), as the schema is then untouched.

        Args:
            *args: Positional arguments passed to ``Model.save()``.
            **kwargs: Keyword arguments passed to ``Model.save()``.
        """
        # Skipped when only some fields are written (e.g. archive metadata), as the schema is then untouched
        if kwargs.get("update_fields") is None:
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Return the name of the template."""
        return self.name


class VisitInstance(TrackingModel):
    """Visit of a folder, filled by the inspector on its own copy of a template.

    The form, the progress and the validation only read ``instance_schema``. The
    answers are stored as ``{"answers": {"<field id>": value}}``. A visit marked
    ``VALIDATED`` or archived is read-only.

    Attributes:
        folder: Folder the visit belongs to.
        template: Template the visit comes from (None if it was deleted).
        template_name: Name of the template when the visit was created.
        instance_schema: Snapshot of the template structure.
        data: Answers of the visit.
        revision: Counter incremented each time answers are saved.
        completed_at: Optional date the visit was finished.
        current_status: Status, see ``Status``.
        due_date: Optional planned date.
        notes: Notes on the visit.
    """

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Planifiée"
        DELAY = "DELAY", "En retard"
        VALIDATED = "VALIDATED", "Effectuée"

    # --- INSPECTION FOLDER RELATIONSHIP ---
    folder = models.ForeignKey(
        "InspectionFolder",
        on_delete=models.CASCADE,
        related_name="visits",
        verbose_name="Dossier associé",
    )
    # The template is only the origin of the visit: the visit works on its own snapshot (instance_schema),
    # so the template can be edited, archived or deleted without any effect on the visit.
    template = models.ForeignKey(
        VisitTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instances",
        verbose_name="Template d'origine",
    )
    template_name = models.CharField(
        max_length=255, blank=True, verbose_name="Nom du template d'origine"
    )
    instance_schema = models.JSONField(
        blank=True, default=dict, verbose_name="Structure de l'instance (JSON)"
    )

    # --- DATA & STATUS ---
    # Answers are stored as {"answers": {"<field id>": value}}, keyed by the ids of instance_schema
    data = models.JSONField(
        blank=True, default=dict, verbose_name="Données saisies (JSON)"
    )
    revision = models.PositiveIntegerField(
        default=0, verbose_name="Révision des réponses"
    )
    completed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de fin de la visite"
    )
    current_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        verbose_name="Statut de la visite",
    )
    due_date = models.DateField(null=True, blank=True, verbose_name="Date de visite")
    notes = models.TextField(blank=True, verbose_name="Notes sur la visite")

    if TYPE_CHECKING:
        # FK id attribute, declared for Pylance only
        folder_id: int

    class Meta(TrackingModel.Meta):
        verbose_name = "Instance de visite"
        verbose_name_plural = "Instances de visite"
        ordering = ["-created_at"]

    def snapshot_template(self) -> None:
        """Freeze the structure and the name of the template into the visit."""
        if self.template:
            self.instance_schema = copy.deepcopy(self.template.schema)
            self.template_name = self.template.name

    def clean(self) -> None:
        """Validate the visit.

        Takes the template snapshot if the visit has no structure yet, then validates
        the structure and the answers against it. Required fields are not enforced
        here, only when the visit is finished (``complete_visit``).

        Raises:
            django.core.exceptions.ValidationError: If the structure is invalid, the
                data is not a JSON object or an answer is invalid.
        """
        super().clean()

        if not self.instance_schema:
            self.snapshot_template()
        validate_template_schema(self.instance_schema)

        if not isinstance(self.data, dict):
            raise ValidationError(
                "Les données de la visite doivent être un objet JSON."
            )
        answers = self.data.get("answers", {})
        # Required fields are only enforced by the "Terminer" action of the form (complete_visit):
        # a visit can also be ticked as done from its planning, e.g. when it was filled elsewhere.
        try:
            cleaned = validate_answers(self.instance_schema, answers)
        except AnswersValidationError as e:
            # A plain error: the keys of the field errors are field ids of the visit, not fields of a form
            raise ValidationError(
                "Réponses invalides : " + " ; ".join(e.field_errors.values())
            )
        self.data = {**self.data, "answers": cleaned}

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the visit, validating it first with ``full_clean()``.

        The validation is skipped when only some fields are written
        (``update_fields``): the answers are validated by the service that writes them.

        Args:
            *args: Positional arguments passed to ``Model.save()``.
            **kwargs: Keyword arguments passed to ``Model.save()``.
        """
        # Skipped when only some fields are written: the answers are validated by the service that writes them
        if kwargs.get("update_fields") is None:
            self.full_clean()
        super().save(*args, **kwargs)

    @property
    def answers(self) -> dict[str, Any]:
        """Return the answers of the visit, ``{field id: value}``, empty if there is none."""
        return self.data.get("answers", {}) if isinstance(self.data, dict) else {}

    @property
    def progress(self) -> dict[str, Any]:
        """Return the progress of the visit, see ``compute_progress()``."""
        return compute_progress(self.instance_schema, self.answers)

    @property
    def is_late(self) -> bool:
        """Tell whether the visit is late: planned and its date is over.

        The stored ``DELAY`` status is still considered late, for existing records.
        """
        if self.current_status == self.Status.DELAY:
            return True
        return (
            self.current_status == self.Status.SCHEDULED
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )

    @property
    def days_until_due(self) -> Optional[int]:
        """Return the days left before the visit date.

        Returns:
            The number of days (negative when the date is over), or None without date.
        """
        if not self.due_date:
            return None
        return (self.due_date - timezone.localdate()).days

    @property
    def display_template_name(self) -> str:
        """Return the template name to display, even if the template was deleted."""
        return self.template_name or (
            self.template.name if self.template else "Template supprimé"
        )

    @property
    def template_is_available(self) -> bool:
        """Tell whether the origin template still exists and is active."""
        return self.template is not None and self.template.is_active

    def __str__(self) -> str:
        """Return the template name and the reference of the folder."""
        return f"Visite {self.display_template_name} - Dossier {self.folder.reference}"


"""

==== INSPECTION RECOMMANDATION SECTION ====

"""


class Recommandation(TrackingModel):
    """Recommendation made to the company after an inspection.

    Attributes:
        folder: Folder the recommendation belongs to.
        description: Text of the recommendation.
        priority: Priority, see ``Priority``.
        current_status: Status, see ``Status``.
        due_date: Optional deadline for the execution.
        topic: Optional subject.
        notes: Notes on the recommendation.
    """

    class Priority(models.TextChoices):
        LOW = "LOW", "Basse"
        MEDIUM = "MEDIUM", "Moyenne"
        HIGH = "HIGH", "Haute"
        CRITICAL = "CRITICAL", "Critique"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Ouverte"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        RESOLVED = "RESOLVED", "Résolue"
        ABANDONED = "ABANDONED", "Abandonnée"

    # --- FOLDER RELATIONSHIP ---
    folder = models.ForeignKey(
        InspectionFolder,
        on_delete=models.CASCADE,
        related_name="recommandations",
        verbose_name="Dossier d'inspection",
    )

    # --- DATA ---
    description = models.TextField(verbose_name="Description de la recommandation")
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        verbose_name="Priorité",
    )
    current_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Statut actuel",
    )
    due_date = models.DateField(
        blank=True, null=True, verbose_name="Date limite d'exécution"
    )
    topic = models.CharField(
        max_length=255, blank=True, verbose_name="Sujet de la recommandation"
    )
    notes = models.TextField(blank=True, verbose_name="Notes sur la recommandation")

    if TYPE_CHECKING:
        # FK id attribute, declared for Pylance only
        folder_id: int

    class Meta(TrackingModel.Meta):
        verbose_name = "Recommandation"
        verbose_name_plural = "Recommandations"
        ordering = ["due_date", "-priority"]

    @property
    def days_until_due(self) -> Optional[int]:
        """Return the days left before the due date.

        Returns:
            The number of days (negative when overdue), or None without due date.
        """
        if not self.due_date:
            return None
        return (self.due_date - timezone.localdate()).days

    def __str__(self) -> str:
        """Return the folder reference, the start of the description and the status."""
        return f"Rec #{self.folder.reference} - {self.description[:50]} : ({self.current_status})"
