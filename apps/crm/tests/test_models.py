"""Tests for the company and contact lifecycle (crm/models.py, crm/services/).

Covers the archiving cascade, the deletion rules, the computed properties and the
company and contact services.
"""

from accounts.tests.factories import UserFactory
from django.db.models import ProtectedError
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone
from inspections.tests.factories import InspectionFolderFactory

from crm.models import Company, Contact
from crm.services.company import (
    get_company_archive_impact,
    get_company_by_id,
    get_filtered_companies,
)
from crm.services.contact import (
    get_contact_archive_impact,
    get_contact_by_id,
    get_filtered_contacts,
)
from crm.tests.factories import CompanyFactory, ContactFactory


def get_request(**params):
    """Build a GET request with query parameters.

    Args:
        **params: Query string parameters.

    Returns:
        The request.
    """
    return RequestFactory().get("/", params)


class CompanyArchiveTests(TestCase):
    """``Company.cascade_archive`` and the absence of reactivation."""

    def setUp(self):
        """Create a company with two contacts, one of them used by an active folder."""
        self.company = CompanyFactory()
        self.user = UserFactory()
        self.free = ContactFactory(company=self.company)
        self.used = ContactFactory(company=self.company)
        self.folder = InspectionFolderFactory(company=self.company, contact=self.used)
        self.already = ContactFactory(company=self.company, archived=True)

    def test_free_contacts_are_archived_with_the_company_date(self):
        """Active contacts without active folder are archived with the same date."""
        self.company.archive(self.user)
        self.free.refresh_from_db()
        self.assertFalse(self.free.is_active)
        self.assertEqual(self.free.archived_at, self.company.archived_at)
        self.assertEqual(self.free.archived_by, self.user)
        self.assertEqual(self.free.updated_by, self.user)

    def test_contact_of_an_active_folder_stays_active(self):
        """A contact referenced by an active folder is not archived."""
        self.company.archive(self.user)
        self.used.refresh_from_db()
        self.assertTrue(self.used.is_active)

    def test_contact_of_an_archived_folder_is_archived(self):
        """Once the folder is archived, its contact follows the company."""
        self.folder.archive(self.user)
        self.company.archive(self.user)
        self.used.refresh_from_db()
        self.assertFalse(self.used.is_active)

    def test_already_archived_contact_keeps_its_date(self):
        """A contact archived earlier is left untouched."""
        previous = self.already.archived_at
        self.company.archive(self.user)
        self.already.refresh_from_db()
        self.assertEqual(self.already.archived_at, previous)

    def test_unarchive_does_not_reactivate_contacts(self):
        """Unarchiving the company leaves its archived contacts archived."""
        self.company.archive(self.user)
        self.company.unarchive(self.user)
        self.free.refresh_from_db()
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertFalse(self.free.is_active)

    def test_archive_impact(self):
        """The impact lists the contacts archived, the ones kept and the active folders."""
        impact = get_company_archive_impact(self.company)
        self.assertEqual(list(impact["contacts"]), [self.free])
        self.assertEqual(list(impact["kept_contacts"]), [self.used])
        self.assertEqual(list(impact["folders"]), [self.folder])


class CompanyDeletionTests(TestCase):
    """Deletion rules of companies and contacts."""

    def test_company_with_a_folder_cannot_be_deleted(self):
        """A company with a folder is protected."""
        folder = InspectionFolderFactory()
        with self.assertRaises(ProtectedError):
            folder.company.delete()

    def test_company_with_an_archived_folder_cannot_be_deleted(self):
        """An archived folder protects the company too."""
        folder = InspectionFolderFactory(archived=True)
        with self.assertRaises(ProtectedError):
            folder.company.delete()

    def test_company_without_folder_deletes_its_contacts(self):
        """Deleting a company without folder deletes its contacts with it."""
        contact = ContactFactory()
        contact.company.delete()
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())

    def test_contact_archive_impact_lists_active_folders(self):
        """The active folders that reference a contact block its archiving."""
        folder = InspectionFolderFactory()
        InspectionFolderFactory(
            company=folder.company, contact=folder.contact, archived=True
        )
        self.assertEqual(list(get_contact_archive_impact(folder.contact)), [folder])


class CompanyPropertiesTests(TestCase):
    """Reference, display properties and head office of ``Company``."""

    def test_reference_is_generated_and_sequential(self):
        """References follow ``SOC-<year>-<number>``, numbered one after the other."""
        year = timezone.now().year
        first = CompanyFactory()
        second = CompanyFactory()
        self.assertEqual(first.reference, f"SOC-{year}-0001")
        self.assertEqual(second.reference, f"SOC-{year}-0002")

    def test_explicit_reference_is_kept(self):
        """A reference given at creation is not replaced."""
        self.assertEqual(CompanyFactory(reference="SOC-X").reference, "SOC-X")

    def test_unparsable_last_reference_restarts_the_numbering(self):
        """A last reference with a non-numeric tail restarts at 1 instead of failing."""
        year = timezone.now().year
        CompanyFactory(reference=f"SOC-{year}-abc")
        self.assertEqual(CompanyFactory().reference, f"SOC-{year}-0001")

    def test_legal_structure_display(self):
        """A known code shows its label, anything else is shown as typed."""
        self.assertEqual(
            CompanyFactory(legal_structure="5499").legal_structure_display,
            "Société à responsabilité limitée (sans autre indication)",
        )
        self.assertEqual(
            CompanyFactory(legal_structure="9999").legal_structure_display, "9999"
        )
        self.assertEqual(
            CompanyFactory(legal_structure="SAS").legal_structure_display, "SAS"
        )
        self.assertEqual(CompanyFactory(legal_structure="").legal_structure_display, "")

    def test_activity_naf25_display(self):
        """The activity is shown as ``label (code)``, or the code alone, or nothing."""
        full = CompanyFactory(
            activity_naf25="62.01Z", activity_naf25_label="Programmation"
        )
        self.assertEqual(full.activity_naf25_display, "Programmation (62.01Z)")
        self.assertEqual(
            CompanyFactory(activity_naf25="62.01Z").activity_naf25_display, "62.01Z"
        )
        self.assertEqual(CompanyFactory().activity_naf25_display, "")

    def test_is_headquarters(self):
        """The establishment is the head office when both SIRET are equal."""
        company = CompanyFactory()
        self.assertFalse(company.is_headquarters)
        company.headquarters_siret = company.siret
        self.assertTrue(company.is_headquarters)
        company.headquarters_siret = "99999999999999"
        self.assertFalse(company.is_headquarters)

    def test_headquarters_company(self):
        """The head office client is found by SIRET when it exists and is another one."""
        head = CompanyFactory()
        branch = CompanyFactory(headquarters_siret=head.siret)
        self.assertEqual(branch.headquarters_company, head)
        self.assertIsNone(head.headquarters_company)
        head.headquarters_siret = head.siret
        self.assertIsNone(head.headquarters_company)
        self.assertIsNone(
            CompanyFactory(headquarters_siret="88888888888888").headquarters_company
        )

    def test_cessation_alert(self):
        """The alert depends on the stored administrative state."""
        self.assertIsNone(CompanyFactory().cessation_alert)
        self.assertIsNone(
            CompanyFactory(
                administrative_state=Company.SireneState.ACTIVE
            ).cessation_alert
        )
        closed = CompanyFactory(
            closed=True, headquarters_state="A", headquarters_address="1 rue X"
        )
        alert = closed.cessation_alert
        self.assertEqual(alert["kind"], "closed")
        self.assertEqual(alert["since"], closed.closure_date)
        self.assertEqual((alert["hq_state"], alert["hq_address"]), ("A", "1 rue X"))
        ceased = CompanyFactory(ceased=True).cessation_alert
        self.assertEqual(ceased["kind"], "ceased")
        self.assertIsNone(ceased["since"])

    def test_cessation_alert_reports_a_closed_head_office(self):
        """The head office state is carried by the alert."""
        alert = CompanyFactory(closed=True, headquarters_state="F").cessation_alert
        self.assertEqual(alert["hq_state"], "F")

    def test_nb_employees_is_optional(self):
        """The number of employees can stay empty."""
        company = CompanyFactory(nb_employees=None)
        company.refresh_from_db()
        self.assertIsNone(company.nb_employees)
        company.full_clean()

    def test_str_methods(self):
        """Companies show their name, contacts their name and company."""
        contact = ContactFactory(first_name="Ada", last_name="Lovelace")
        self.assertEqual(str(contact.company), contact.company.name)
        self.assertEqual(str(contact), f"Ada Lovelace - {contact.company.name}")


class CompanyServicesTests(TestCase):
    """``get_company_by_id`` and ``get_filtered_companies``."""

    @classmethod
    def setUpTestData(cls):
        """Create an active company with two folders, a quiet one and an archived one."""
        cls.busy = CompanyFactory(
            name="Zeta Busy", siret="11111111111111", siren="111111111"
        )
        InspectionFolderFactory.create_batch(2, company=cls.busy)
        cls.quiet = CompanyFactory(
            name="Alpha Quiet", siret="22222222222222", siren="222222222"
        )
        cls.archived = CompanyFactory(name="Mid Archived", archived=True)

    def test_get_company_by_id(self):
        """An existing company is returned, a missing one gives a 404."""
        self.assertEqual(get_company_by_id(self.busy.pk), self.busy)
        with self.assertRaises(Http404):
            get_company_by_id(0)

    def test_default_list_is_active_companies_by_name(self):
        """By default archived companies are hidden and the list is sorted by name."""
        self.assertEqual(
            list(get_filtered_companies(get_request())), [self.quiet, self.busy]
        )

    def test_status_filter(self):
        """``archived`` shows the archived companies only."""
        self.assertEqual(
            list(get_filtered_companies(get_request(status="archived"))),
            [self.archived],
        )

    def test_search_on_name_siren_siret_reference(self):
        """The search matches the name, the SIREN, the SIRET and the reference."""
        for query in ("zeta", "111111111", "11111111111111", self.busy.reference):
            with self.subTest(query=query):
                found = get_filtered_companies(get_request(q=query))
                self.assertEqual(list(found), [self.busy])

    def test_sort_whitelist(self):
        """The folder count sort works, an unknown sort falls back to the name."""
        by_count = get_filtered_companies(get_request(sort="-inspection_folders_count"))
        self.assertEqual(by_count[0], self.busy)
        self.assertEqual(by_count[0].inspection_folders_count, 2)
        fallback = get_filtered_companies(get_request(sort="siret; DROP"))
        self.assertEqual(list(fallback), [self.quiet, self.busy])


class ContactServicesTests(TestCase):
    """``get_contact_by_id`` and ``get_filtered_contacts``."""

    @classmethod
    def setUpTestData(cls):
        """Create contacts in two companies, one of them archived."""
        cls.acme = CompanyFactory(name="Acme")
        cls.globex = CompanyFactory(name="Globex")
        cls.ada = ContactFactory(
            company=cls.acme,
            first_name="Ada",
            last_name="Lovelace",
            email="ada@acme.fr",
        )
        cls.bob = ContactFactory(
            company=cls.globex, first_name="Bob", last_name="Martin"
        )
        cls.old = ContactFactory(
            company=cls.acme, first_name="Old", last_name="One", archived=True
        )

    def test_get_contact_by_id(self):
        """An existing contact is returned, a missing one gives a 404."""
        self.assertEqual(get_contact_by_id(self.ada.pk), self.ada)
        with self.assertRaises(Http404):
            get_contact_by_id(0)

    def test_default_list_is_active_newest_first(self):
        """By default only active contacts are listed, newest first."""
        self.assertEqual(
            list(get_filtered_contacts(get_request())), [self.bob, self.ada]
        )

    def test_status_filter(self):
        """``archived`` lists archived contacts, any other value lists all of them."""
        self.assertEqual(
            list(get_filtered_contacts(get_request(status="archived"))), [self.old]
        )
        self.assertEqual(len(get_filtered_contacts(get_request(status="all"))), 3)

    def test_search(self):
        """The search matches the names, the email and the company name."""
        for query in ("lovelace", "ada@acme", "globex"):
            with self.subTest(query=query):
                found = list(get_filtered_contacts(get_request(q=query)))
                self.assertEqual(found, [self.ada if query != "globex" else self.bob])

    def test_company_filter_ignores_non_numeric_ids(self):
        """The company filter applies for a numeric id and is ignored otherwise."""
        self.assertEqual(
            list(get_filtered_contacts(get_request(company=self.globex.pk))), [self.bob]
        )
        self.assertEqual(len(get_filtered_contacts(get_request(company="abc"))), 2)
