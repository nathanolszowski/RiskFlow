"""Abstract base model shared by the business models of the project."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from django.conf import settings
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from accounts.models import CustomUser


class AddressMixin(models.Model):
    """Abstract postal address that can be certified by the geocoding service.

    ``address_line``, ``postal_code`` and ``city`` are typed by the user. The other
    fields are never editable in forms: they are set by
    ``core.services.geo.certify_address`` from the geocoder answer, so coordinates
    cannot come from a posted form.

    Attributes:
        address_line: Number and street.
        postal_code: Postal code.
        city: City.
        citycode: INSEE code of the municipality, given by the geocoder or Sirene.
        latitude: Latitude of the geocoded address (WGS84).
        longitude: Longitude of the geocoded address (WGS84).
        address_certified: True when the geocoder found the address with enough confidence.
        address_source: Where the current address comes from.
        geocoded_at: Date of the last geocoding attempt, empty if never tried.
        geocoded_address: Address text the coordinates were computed for. When it
            differs from ``full_address`` the coordinates are stale: ``save()``
            clears them and ``certify_address`` computes them again.
    """

    ADDRESS_PARTS = ("address_line", "postal_code", "city")
    GEOCODING_FIELDS = (
        "latitude",
        "longitude",
        "address_certified",
        "geocoded_at",
        "geocoded_address",
        "citycode",
    )

    class AddressSource(models.TextChoices):
        """Origin of the address."""

        MANUAL = "manual", "Saisie"
        SIRENE = "sirene", "Sirene"

    address_line = models.CharField(
        max_length=255, blank=True, verbose_name="Numéro et rue"
    )
    postal_code = models.CharField(
        max_length=10, blank=True, verbose_name="Code postal"
    )
    city = models.CharField(max_length=100, blank=True, verbose_name="Ville")
    citycode = models.CharField(
        max_length=5, blank=True, editable=False, verbose_name="Code commune (INSEE)"
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Latitude",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Longitude",
    )
    address_certified = models.BooleanField(
        default=False, editable=False, verbose_name="Adresse certifiée"
    )
    address_source = models.CharField(
        max_length=10,
        choices=AddressSource.choices,
        default=AddressSource.MANUAL,
        editable=False,
        verbose_name="Origine de l'adresse",
    )
    geocoded_at = models.DateTimeField(
        null=True, blank=True, editable=False, verbose_name="Date du géocodage"
    )
    geocoded_address = models.CharField(
        max_length=400, blank=True, editable=False, verbose_name="Adresse géocodée"
    )

    class Meta:
        abstract = True

    @property
    def full_address(self) -> str:
        """Return the address on one line (``12 rue X, 75001 Paris``), empty if unset."""
        locality = f"{self.postal_code} {self.city}".strip()
        return ", ".join(part for part in (self.address_line, locality) if part)

    @property
    def has_coordinates(self) -> bool:
        """Return whether the address has been geocoded."""
        return self.latitude is not None and self.longitude is not None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save, dropping the coordinates when the address changed since the geocoding.

        No network call here: ``core.services.geo.certify_address`` computes the new
        coordinates. A partial save (``update_fields``) is extended with the cleared
        fields only when it writes the address.

        Args:
            *args: Positional arguments passed to ``Model.save()``.
            **kwargs: Keyword arguments passed to ``Model.save()``.
        """
        update_fields = kwargs.get("update_fields")
        writes_address = update_fields is None or bool(
            set(self.ADDRESS_PARTS) & set(update_fields)
        )
        if writes_address and self.full_address != self.geocoded_address:
            self.latitude = None
            self.longitude = None
            self.address_certified = False
            if update_fields is not None:
                kwargs["update_fields"] = [
                    *update_fields,
                    "latitude",
                    "longitude",
                    "address_certified",
                ]
        super().save(*args, **kwargs)


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
