"""Profile of the logged-in user: e-mail, home address and password."""

from django.contrib.auth import update_session_auth_hash
from django.http import HttpRequest
from django.utils import timezone

from accounts.models import CustomUser

ADDRESS_FIELDS = ("street", "address_complement", "postal_code", "city")


def get_inspector_profile(user: CustomUser):
    """Return the inspector profile of ``user``, or None if there is none."""
    return getattr(user, "inspector_profile", None)


def update_email(user: CustomUser, email: str) -> CustomUser:
    """Save the e-mail address of ``user``."""
    user.email = email
    user.save(update_fields=["email"])
    return user


def update_address(user: CustomUser, data: dict) -> CustomUser:
    """Save the home address of ``user`` from the cleaned form data."""
    for field in ADDRESS_FIELDS:
        setattr(user, field, data.get(field, ""))
    user.save(update_fields=list(ADDRESS_FIELDS))
    return user


def change_password(request: HttpRequest, form) -> CustomUser:
    """Save a valid password form, stamp the date and keep the session open.

    Args:
        request: Current request (its session survives the password change).
        form: Validated ``PasswordChangeForm``.

    Returns:
        The user with the new password.
    """
    user = form.save(commit=False)
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password", "password_changed_at"])
    update_session_auth_hash(request, user)
    return user
