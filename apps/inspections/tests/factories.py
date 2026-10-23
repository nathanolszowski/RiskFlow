"""Factories of the inspections app (inspections/models.py)."""

from copy import deepcopy
from datetime import timedelta

import factory
from core.tests.factories import TrackedFactory
from crm.tests.factories import CompanyFactory, ContactFactory
from django.utils import timezone

from inspections.models import (
    InspectionFolder,
    Recommandation,
    VisitInstance,
    VisitTemplate,
)

SAMPLE_SCHEMA = {
    "version": "1.0",
    "sections": [
        {
            "id": "s_general",
            "title": "Généralités",
            "order": 1,
            "fields": [
                {
                    "id": "f_acces_libre",
                    "label": "Accès libre au site",
                    "type": "boolean",
                    "required": True,
                    "order": 1,
                },
                {
                    "id": "f_observation",
                    "label": "Observation générale",
                    "type": "text",
                    "required": True,
                    "order": 2,
                },
            ],
        },
        {
            "id": "s_mesures",
            "title": "Mesures",
            "order": 2,
            "fields": [
                {
                    "id": "f_niveau",
                    "label": "Niveau de risque",
                    "type": "select",
                    "required": True,
                    "options": ["faible", "moyen", "élevé"],
                    "order": 1,
                },
                {
                    "id": "f_mesure",
                    "label": "Température relevée",
                    "type": "number",
                    "required": True,
                    "unit": "°C",
                    "min": 0,
                    "max": 100,
                    "order": 2,
                },
                {
                    "id": "f_remarques",
                    "label": "Remarques",
                    "type": "text",
                    "required": False,
                    "order": 3,
                },
            ],
        },
    ],
}
"""Template structure used by the tests: 2 sections, 5 fields (4 required, 1 optional)."""


class InspectionFolderFactory(TrackedFactory):
    """Build a valid ``InspectionFolder`` for a client and one of its contacts.

    The contact always belongs to the folder's company, so ``InspectionFolder.clean()``
    passes. The whole tree has a single owner: ``created_by``, who also creates the
    company and the contact.

    Attributes:
        created_by: Owner of the folder, a new user by default. Pass it to build the
            whole tree for a given user.
        company: A new company created by ``created_by``.
        contact: A new contact of that company, created by ``created_by``.

    Traits:
        archived: Archived folder (see ``TrackedFactory``).
    """

    class Meta:
        """Bind the factory to the folder model."""

        model = InspectionFolder

    created_by = factory.SubFactory("accounts.tests.factories.UserFactory")
    company = factory.SubFactory(
        CompanyFactory, created_by=factory.SelfAttribute("..created_by")
    )
    contact = factory.SubFactory(
        ContactFactory,
        company=factory.SelfAttribute("..company"),
        created_by=factory.SelfAttribute("..created_by"),
    )
    address_line = factory.Faker("street_address")
    postal_code = factory.Faker("postcode")
    city = factory.Faker("city")


class VisitTemplateFactory(TrackedFactory):
    """Build a valid ``VisitTemplate`` holding a copy of ``SAMPLE_SCHEMA``.

    Attributes:
        created_by: A new user (pass one to give several templates the same owner).
        shared: False by default (model field).
        schema: A deep copy of ``SAMPLE_SCHEMA``, safe to modify in a test.

    Traits:
        archived: Archived template (see ``TrackedFactory``).
        shared_template: Template shared with every user (``shared=True``). The
            trait cannot be called ``shared``: factory_boy refuses a trait that has
            the name of a field.
    """

    class Meta:
        """Bind the factory to the template model."""

        model = VisitTemplate

    class Params:
        """Traits of the template factory."""

        shared_template = factory.Trait(shared=True)

    created_by = factory.SubFactory("accounts.tests.factories.UserFactory")
    name = factory.Sequence(lambda n: f"Template {n}")
    shared = False
    schema = factory.LazyFunction(lambda: deepcopy(SAMPLE_SCHEMA))


class VisitInstanceFactory(TrackedFactory):
    """Build a valid ``VisitInstance`` created from a template, like ``create_visit``.

    Attributes:
        folder: A new folder by default.
        template: A template owned by the folder's owner.
        instance_schema: Copy of the template schema (the snapshot).
        template_name: Name of the template.
        data: No answer yet (``{"answers": {}}``).
        created_by: The owner of the folder.

    Traits:
        archived: Archived visit (see ``TrackedFactory``).
        validated: Visit marked done (``VALIDATED`` with ``completed_at``).
        late: Scheduled visit whose ``due_date`` is three days ago.
    """

    class Meta:
        """Bind the factory to the visit model."""

        model = VisitInstance

    class Params:
        """Traits of the visit factory."""

        validated = factory.Trait(
            current_status=VisitInstance.Status.VALIDATED,
            completed_at=factory.LazyFunction(timezone.now),
        )
        late = factory.Trait(
            current_status=VisitInstance.Status.SCHEDULED,
            due_date=factory.LazyFunction(
                lambda: timezone.localdate() - timedelta(days=3)
            ),
        )

    folder = factory.SubFactory(InspectionFolderFactory)
    created_by = factory.SelfAttribute("folder.created_by")
    template = factory.SubFactory(
        VisitTemplateFactory, created_by=factory.SelfAttribute("..created_by")
    )
    instance_schema = factory.LazyAttribute(lambda o: deepcopy(o.template.schema))
    template_name = factory.LazyAttribute(lambda o: o.template.name)
    data = factory.LazyFunction(lambda: {"answers": {}})


class RecommandationFactory(TrackedFactory):
    """Build a valid ``Recommandation`` of a folder.

    Attributes:
        folder: A new folder by default.
        created_by: The owner of the folder.

    Traits:
        archived: Archived recommendation (see ``TrackedFactory``).
    """

    class Meta:
        """Bind the factory to the recommendation model."""

        model = Recommandation

    folder = factory.SubFactory(InspectionFolderFactory)
    created_by = factory.SelfAttribute("folder.created_by")
    description = factory.Faker("sentence")
    topic = "Protection incendie"
