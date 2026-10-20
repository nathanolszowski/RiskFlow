"""Tests for the test factories themselves (every app's ``tests/factories.py``).

The ``save()`` methods call ``full_clean()`` / ``clean()``, so a factory that
builds an object proves that the object is valid.
"""

from accounts.models import CustomUser
from accounts.tests.factories import UserFactory
from crm.models import Company
from crm.tests.factories import CompanyFactory, ContactFactory
from django.test import TestCase
from inspections.models import VisitInstance
from inspections.tests.factories import (
    InspectionFolderFactory,
    RecommandationFactory,
    VisitInstanceFactory,
    VisitTemplateFactory,
)
from medias.tests.factories import MediaFactory, MediaTagFactory


class FactoriesTests(TestCase):
    """Build one object per factory and per trait (no setup data)."""

    def test_user_factory_sets_a_usable_password(self):
        """A user can log in with the password ``password``."""
        user = UserFactory()
        self.assertTrue(user.check_password("password"))

    def test_company_factory_generates_reference_and_siren(self):
        """A company gets a generated reference and a SIREN taken from its SIRET."""
        company = CompanyFactory()
        self.assertTrue(company.reference.startswith("SOC-"))
        self.assertEqual(company.siren, company.siret[:9])

    def test_company_traits(self):
        """The closed and ceased traits set the administrative state."""
        self.assertEqual(CompanyFactory(closed=True).administrative_state, "F")
        self.assertIsNotNone(CompanyFactory(closed=True).closure_date)
        self.assertEqual(CompanyFactory(ceased=True).administrative_state, "C")

    def test_contact_belongs_to_the_owner_of_its_company(self):
        """A contact is created by the creator of its company."""
        contact = ContactFactory()
        self.assertEqual(contact.created_by_id, contact.company.created_by_id)

    def test_folder_factory_builds_a_tree_with_a_single_user(self):
        """A default folder tree (company, contact, folder) has exactly one user."""
        folder = InspectionFolderFactory()
        self.assertEqual(CustomUser.objects.count(), 1)
        self.assertEqual(folder.contact.company_id, folder.company_id)
        self.assertEqual(folder.created_by_id, folder.company.created_by_id)
        self.assertRegex(folder.reference, r"^DOS-\d{4}-[0-9A-F]{6}$")

    def test_template_factory_and_shared_trait(self):
        """A template is valid, private by default and shared with the trait."""
        self.assertFalse(VisitTemplateFactory().shared)
        self.assertTrue(VisitTemplateFactory(shared_template=True).shared)

    def test_templates_do_not_share_their_schema(self):
        """Editing the schema of one template never leaks to another one."""
        first = VisitTemplateFactory()
        first.schema["sections"].clear()
        self.assertTrue(VisitTemplateFactory().schema["sections"])

    def test_visit_factory_takes_a_snapshot_of_the_template(self):
        """A visit copies the schema and name of its template, with no answer."""
        visit = VisitInstanceFactory()
        self.assertEqual(visit.instance_schema, visit.template.schema)
        self.assertIsNot(visit.instance_schema, visit.template.schema)
        self.assertEqual(visit.template_name, visit.template.name)
        self.assertEqual(visit.answers, {})
        self.assertEqual(CustomUser.objects.count(), 1)

    def test_visit_traits(self):
        """The validated and late traits set the status, the date and completion."""
        validated = VisitInstanceFactory(validated=True)
        self.assertEqual(validated.current_status, VisitInstance.Status.VALIDATED)
        self.assertIsNotNone(validated.completed_at)
        self.assertTrue(VisitInstanceFactory(late=True).is_late)

    def test_recommandation_and_media_factories(self):
        """Recommendations, medias and tags are created for the folder owner."""
        recommandation = RecommandationFactory()
        media = MediaFactory()
        tag = MediaTagFactory()
        self.assertEqual(
            recommandation.created_by_id, recommandation.folder.created_by_id
        )
        self.assertEqual(media.created_by_id, media.folder.created_by_id)
        self.assertTrue(media.file.name.startswith(f"folders/{media.folder_id}/"))
        self.assertTrue(tag.name)

    def test_archived_trait_on_every_tracked_factory(self):
        """The archived trait deactivates and dates the object on every factory."""
        factories = [
            CompanyFactory,
            ContactFactory,
            InspectionFolderFactory,
            VisitTemplateFactory,
            VisitInstanceFactory,
            RecommandationFactory,
            MediaFactory,
            MediaTagFactory,
        ]
        for factory_class in factories:
            with self.subTest(factory=factory_class.__name__):
                obj = factory_class(archived=True)
                self.assertFalse(obj.is_active)
                self.assertIsNotNone(obj.archived_at)
                self.assertEqual(obj.archived_by_id, obj.created_by_id)

    def test_company_references_are_unique(self):
        """Successive companies get distinct references and SIRET numbers."""
        companies = CompanyFactory.create_batch(3)
        self.assertEqual(len({c.reference for c in companies}), 3)
        self.assertEqual(Company.objects.count(), 3)
