"""Profile of the logged-in user: e-mail, home address and password."""

from core.services.geo import certify_address
from django.utils import timezone

from accounts.models import CustomUser

ADDRESS_FIELDS = ("address_line", "address_complement", "postal_code", "city")


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
    certify_address(user)
    return user


def change_password(user: CustomUser, form) -> CustomUser:
    """Save a valid password form of ``user`` and stamp the date of the change.

    The view keeps the session open (``update_session_auth_hash``).

    Args:
        user: User changing the password.
        form: Validated ``PasswordChangeForm`` of that user.

    Returns:
        The user with the new password.
    """
    user = form.save(commit=False)
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password", "password_changed_at"])
    return user
