"""Factories of the accounts app (accounts/models.py)."""

import factory
from factory.declarations import (
    LazyAttribute,
    PostGenerationMethodCall,
    Sequence,
)

from accounts.models import CustomUser


class UserFactory(factory.django.DjangoModelFactory):
    """Build a ``CustomUser`` with a unique username and the password ``"password"``.

    Attributes:
        username: ``user0``, ``user1``... (unique through a sequence).
        email: ``user<n>@example.com``.
        password: Always ``"password"``, hashed with ``set_password`` so that
            ``client.login`` and ``client.force_login`` both work.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Bind the factory to the user model."""

        model = CustomUser
        skip_postgeneration_save = False

    username = Sequence(lambda n: f"user{n}")
    email = LazyAttribute(lambda o: f"{o.username}@example.com")
    password = PostGenerationMethodCall("set_password", "password")
