"""Tests for the global search (``core/services/search.py`` and ``core:global_search``)."""

from crm.tests.factories import CompanyFactory, ContactFactory
from django.test import TestCase
from django.urls import reverse
from inspections.tests.factories import InspectionFolderFactory

from core.services.search import global_search
from core.tests.helpers import HtmxClientMixin


class GlobalSearchTests(HtmxClientMixin, TestCase):
    """Folders stay private, clients and contacts are shared."""

    def setUp(self):
        """Create a client of another user, its contact and a folder for each user."""
        super().setUp()
        self.company = CompanyFactory(name="Fonderie Zéphyr", created_by=self.other)
        self.contact = ContactFactory(company=self.company, last_name="Zéphyrin")
        self.mine = InspectionFolderFactory(company=self.company, created_by=self.owner)
        self.theirs = InspectionFolderFactory(
            company=self.company, created_by=self.other
        )

    def test_finds_own_folders_and_shared_clients_and_contacts(self):
        """The folders of the user, every client and every contact match."""
        results = global_search(self.owner, "zéphyr")
        self.assertEqual(list(results["folders"]), [self.mine])
        self.assertEqual(list(results["companies"]), [self.company])
        self.assertEqual(list(results["contacts"]), [self.contact])

    def test_short_query_searches_nothing(self):
        """Under two characters (spaces ignored) nothing is searched."""
        results = global_search(self.owner, " z ")
        self.assertEqual(results, {"folders": [], "companies": [], "contacts": []})

    def test_view_renders_the_results(self):
        """The view renders the partial with the query and the results."""
        response = self.htmx_get(reverse("core:global_search"), {"q": "Zéphyr"})
        self.assertTemplateUsed(response, "core/partials/search/search_results.html")
        self.assertEqual(response.context["query"], "Zéphyr")
        self.assertEqual(list(response.context["folders"]), [self.mine])
