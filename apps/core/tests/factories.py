"""Base factory shared by the factories of every ``TrackingModel`` (core/models.py)."""

import factory
from django.utils import timezone
from factory.declarations import LazyFunction, SelfAttribute, Trait


class TrackedFactory(factory.django.DjangoModelFactory):
    """Abstract factory of the ``TrackingModel`` children, providing the archived trait.

    Subclasses must define ``created_by`` (mandatory on ``TrackingModel``).

    Traits:
        archived: ``is_active=False`` with ``archived_at`` set to now and
            ``archived_by`` set to the creator, like ``TrackingModel.archive()``.
    """

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Mark the factory as abstract: it builds no model by itself."""

        abstract = True

    class Params:
        """Traits shared by all tracked factories."""

        archived = Trait(
            is_active=False,
            archived_at=LazyFunction(timezone.now),
            archived_by=SelfAttribute("created_by"),
        )
