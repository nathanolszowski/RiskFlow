"""Factories of the crm app (crm/models.py)."""

from datetime import timedelta

from accounts.tests.factories import UserFactory
from core.tests.factories import TrackedFactory
from django.utils import timezone
from factory.declarations import (
    LazyAttribute,
    LazyFunction,
    SelfAttribute,
    Sequence,
    SubFactory,
    Trait,
)
from factory.faker import Faker

from crm.models import Company, Contact


class CompanyFactory(TrackedFactory):
    """Build a valid ``Company`` (client) owned by a new user.

    Attributes:
        created_by: A new user, also used as ``updated_by``.
        siret: Unique 14-digit number from a sequence; ``siren`` is its first 9 digits.
        reference: Left empty on purpose, ``Company.save()`` generates it.

    Traits:
        archived: Archived company (see ``TrackedFactory``).
        closed: Establishment closed (``administrative_state="F"``) with a
            ``closure_date``.
        ceased: Whole company ceased (``administrative_state="C"``).
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Bind the factory to the company model."""

        model = Company

    class Params:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Traits of the company factory."""

        closed = Trait(
            administrative_state=Company.SireneState.CLOSED,
            closure_date=LazyFunction(
                lambda: timezone.localdate() - timedelta(days=365)
            ),
        )
        ceased = Trait(administrative_state=Company.SireneState.CEASED)

    created_by = SubFactory(UserFactory)
    updated_by = SelfAttribute("created_by")
    name = Faker("company")
    address_line = Faker("street_address")
    postal_code = Faker("postcode")
    city = Faker("city")
    siret = Sequence(lambda n: f"{10_000_000_000_000 + n}")
    siren = LazyAttribute(lambda o: o.siret[:9])
    business_line = "Industrie"
    company_size_category = "PME"
    creation_date = Faker("date_object")


class ContactFactory(TrackedFactory):
    """Build a valid ``Contact`` of a company.

    Attributes:
        company: A new company by default.
        created_by: The creator of the company, so that the whole tree has a
            single owner.

    Traits:
        archived: Archived contact (see ``TrackedFactory``).
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Bind the factory to the contact model."""

        model = Contact

    company = SubFactory(CompanyFactory)
    created_by = SelfAttribute("company.created_by")
    first_name = Faker("first_name")
    last_name = Faker("last_name")
    email = Sequence(lambda n: f"contact{n}@example.com")
    position = "Responsable sécurité"
