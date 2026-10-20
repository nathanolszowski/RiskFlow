"""Factories of the accounts app (accounts/models.py)."""

import factory

from accounts.models import CustomUser


class UserFactory(factory.django.DjangoModelFactory):
    """Build a ``CustomUser`` with a unique username and the password ``"password"``.

    Attributes:
        username: ``user0``, ``user1``... (unique through a sequence).
        email: ``user<n>@example.com``.
        password: Always ``"password"``, hashed with ``set_password`` so that
            ``client.login`` and ``client.force_login`` both work.
    """

    class Meta:
        """Bind the factory to the user model."""

        model = CustomUser
        skip_postgeneration_save = False

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "password")
