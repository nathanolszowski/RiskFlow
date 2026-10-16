"""User model of the project and the inspector profile."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """User of the application, set as ``AUTH_USER_MODEL``.

    Extends Django's ``AbstractUser`` with fields common to all users.

    Attributes:
        phone_number: Optional phone number.
    """

    # Add any additional fields you want for ALL USERS
    phone_number = models.CharField(max_length=15, blank=True, null=True)

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
