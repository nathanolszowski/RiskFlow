"""Abstract base model shared by the business models of the project."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from accounts.models import CustomUser


class TrackingModel(models.Model):
    """Abstract base model that tracks creation, modification and archiving of records.

    Almost every business model inherits from it. ``created_by`` is mandatory, so
    it must always be set when an instance is created. Views should archive
    through ``archive()`` / ``unarchive()`` rather than editing ``is_active`` by
    hand: archiving is a soft delete and always comes before a permanent deletion.

    Attributes:
        created_at: Creation date, set automatically.
        updated_at: Date of the last update, set automatically.
        archived_at: Archiving date, empty while the record is not archived.
        is_active: False once the record is archived.
        created_by: User who created the record (required).
        updated_by: User who last modified the record.
        archived_by: User who archived the record, empty while it is not archived.
    """

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Dernière mise à jour"
    )
    archived_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Date d'archivage"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    # '%(class)s' will be replaced by the lowercased name of the child model that inherits from this abstract model.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_%(class)s_set",
        verbose_name="Créé par",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_%(class)s_set",
        verbose_name="Modifié en dernier par",
        blank=True,
        null=True,
    )

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="archived_%(class)s_set",
        verbose_name="Archivé par",
        blank=True,
        null=True,
    )

    class Meta:
        abstract = True  # <--- Django will not create a database table for this model, but other models can inherit from it to get these fields.

    def archive(self, user: Optional["CustomUser"] = None) -> None:
        """Archive (soft delete) the instance.

        Sets ``is_active`` to False, records the current time in ``archived_at``
        and, when given, the user who performed the action. Then calls
        ``cascade_archive()`` so that child classes can propagate the action.

        Args:
            user: User performing the action, recorded as ``archived_by`` and
                ``updated_by``.
        """
        self.is_active = False
        self.archived_at = timezone.now()
        if user:
            self.archived_by = user
            self.updated_by = user
        self.save()
        self.cascade_archive(user=user)

    def cascade_archive(self, user: Optional["CustomUser"] = None) -> None:
        """Propagate the archiving to related records (hook, does nothing by default).

        To be overridden in child classes when needed. Children should receive
        the same ``archived_at`` as the parent.

        Args:
            user: User performing the action.
        """
        pass

    def unarchive(self, user: Optional["CustomUser"] = None) -> None:
        """Unarchive the instance.

        Sets ``is_active`` to True, clears ``archived_at`` and ``archived_by`` and,
        when given, records the user who performed the action. The previous
        archive date is passed to ``cascade_unarchive()`` so that only the related
        records archived together with this instance are restored.

        Args:
            user: User performing the action, recorded as ``updated_by``.
        """
        previous_archived_at = self.archived_at
        self.is_active = True
        self.archived_at = None
        self.archived_by = None
        if user:
            self.updated_by = user
        self.save()
        self.cascade_unarchive(archived_at=previous_archived_at, user=user)

    def cascade_unarchive(
        self,
        archived_at: Optional[datetime] = None,
        user: Optional["CustomUser"] = None,
    ) -> None:
        """Propagate the unarchiving to related records (hook, does nothing by default).

        To be overridden in child classes when needed.

        Args:
            archived_at: Archive date the instance had before being unarchived,
                used to restore only the records archived together with it.
            user: User performing the action.
        """
        pass
