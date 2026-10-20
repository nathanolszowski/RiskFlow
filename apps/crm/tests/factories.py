"""Factories of the crm app (crm/models.py)."""

from datetime import timedelta

import factory
from accounts.tests.factories import UserFactory
from core.tests.factories import TrackedFactory
from django.utils import timezone

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

    class Meta:
        """Bind the factory to the company model."""

        model = Company

    class Params:
        """Traits of the company factory."""

        closed = factory.Trait(
            administrative_state=Company.SireneState.CLOSED,
            closure_date=factory.LazyFunction(
                lambda: timezone.localdate() - timedelta(days=365)
            ),
        )
        ceased = factory.Trait(administrative_state=Company.SireneState.CEASED)

    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SelfAttribute("created_by")
    name = factory.Faker("company")
    address = factory.Faker("address")
    siret = factory.Sequence(lambda n: f"{10_000_000_000_000 + n}")
    siren = factory.LazyAttribute(lambda o: o.siret[:9])
    business_line = "Industrie"
    company_size_category = "PME"
    creation_date = factory.Faker("date_object")


class ContactFactory(TrackedFactory):
    """Build a valid ``Contact`` of a company.

    Attributes:
        company: A new company by default.
        created_by: The creator of the company, so that the whole tree has a
            single owner.

    Traits:
        archived: Archived contact (see ``TrackedFactory``).
    """

    class Meta:
        """Bind the factory to the contact model."""

        model = Contact

    company = factory.SubFactory(CompanyFactory)
    created_by = factory.SelfAttribute("company.created_by")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Sequence(lambda n: f"contact{n}@example.com")
    position = "Responsable sécurité"
