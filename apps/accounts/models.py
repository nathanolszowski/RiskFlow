"""User model of the project and the inspector profile."""

from core.models import AddressMixin
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser, AddressMixin):
    """User of the application, set as ``AUTH_USER_MODEL``.

    Extends Django's ``AbstractUser`` with fields common to all users. The home
    address (``address_line``, ``postal_code``, ``city`` and the geocoding fields)
    comes from ``AddressMixin``: it is the default starting point of travel times.

    Attributes:
        phone_number: Optional phone number.
        address_complement: Optional address complement (building, floor...).
        password_changed_at: When the user last changed the password themselves.
    """

    # Add any additional fields you want for ALL USERS
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address_complement = models.CharField(
        max_length=255, blank=True, verbose_name="Complément d'adresse"
    )
    password_changed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        """Return the username."""
        return self.username


class Inspector(models.Model):
    """Profile of a user who carries out inspections.

    Attributes:
        user: Related user account.
        registration_number: Unique inspector card number.
        zone: Optional inspection zone.
        is_active: Whether the profile is activated.
    """

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="inspector_profile"
    )

    registration_number = models.CharField(
        max_length=50, unique=True, verbose_name="Card number"
    )
    zone = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Inspection Zone"
    )
    is_active = models.BooleanField(default=True, verbose_name="Activated")

    def __str__(self) -> str:
        """Return the inspector label built from the user's full name or username."""
        return f"Inspecteur : {self.user.get_full_name() or self.user.username}"
