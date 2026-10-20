"""Tests for the archive and delete views of folders, clients, contacts, visits and recommendations.

They share the generic confirmation modal ``core/partials/modal/archive_confirm_modal.html``
(see ``core/modals.py``): GET renders it, POST runs the action. Medias are covered by
``medias/tests/test_views.py``.
"""

from crm.models import Company, Contact
from crm.tests.factories import CompanyFactory, ContactFactory
from django.test import TestCase
from django.urls import reverse
from inspections.models import InspectionFolder, Recommandation, VisitInstance
from inspections.tests.factories import (
    InspectionFolderFactory,
    RecommandationFactory,
    VisitInstanceFactory,
)
from medias.tests.factories import MediaFactory

from core.tests.helpers import HtmxClientMixin

MODAL = "core/partials/modal/archive_confirm_modal.html"
VISIT_TAB = "inspections/partials/tabs/tab_visit.html"
REC_TAB = "inspections/partials/tabs/tab_recommandations.html"


class ModalAssertionsMixin:
    """Assertions on the context of the confirmation modal."""

    def assertModal(self, response, *, blocking):
        """Check a response is the confirmation modal, with or without blocking message.

        Args:
            response: Response of a GET on an archive or delete URL.
            blocking: True if the modal must carry a blocking message (and so no
                confirmation button), False if it must offer the confirmation.
        """
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, MODAL)
        # Regression: a context key named like a dict method would be read as dict.items()
        self.assertNotIn("items", response.context)
        self.assertIn("post_url", response.context)
        if blocking:
            self.assertTrue(response.context["blocking"])
            self.assertNotContains(response, "hx-post=")
        else:
            self.assertFalse(response.context.get("blocking"))
            self.assertContains(response, f'hx-post="{response.context["post_url"]}"')


class FolderArchiveDeleteTests(ModalAssertionsMixin, HtmxClientMixin, TestCase):
    """``folder_archive``, ``folder_unarchive`` and ``folder_delete``."""

    def setUp(self):
        """Create a folder with a visit, a recommendation and a media."""
        super().setUp()
        self.folder = InspectionFolderFactory(created_by=self.owner)
        kwargs = {"folder": self.folder, "created_by": self.owner}
        self.visit = VisitInstanceFactory(**kwargs)
        self.rec = RecommandationFactory(**kwargs)
        self.media = MediaFactory(**kwargs)
        self.archive_url = reverse("inspections:folder_archive", args=[self.folder.pk])
        self.unarchive_url = reverse(
            "inspections:folder_unarchive", args=[self.folder.pk]
        )
        self.delete_url = reverse("inspections:folder_delete", args=[self.folder.pk])

    def test_archive_get_renders_the_modal_with_the_impact(self):
        """The modal counts what will be archived with the folder."""
        response = self.htmx_get(self.archive_url)
        self.assertModal(response, blocking=False)
        entries = response.context["sections"][0]["entries"]
        self.assertEqual(entries, ["1 visite", "1 recommandation", "1 média"])
        self.assertEqual(response.context["object_label"], self.folder.reference)
        self.assertEqual(response.context["post_url"], self.archive_url)

    def test_archive_post_archives_the_tree_and_refreshes(self):
        """POST archives the folder and its children, and asks for a refresh."""
        response = self.htmx_post(self.archive_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        self.folder.refresh_from_db()
        self.assertFalse(self.folder.is_active)
        self.assertEqual(self.folder.archived_by, self.owner)
        for obj in (self.visit, self.rec, self.media):
            obj.refresh_from_db()
            self.assertFalse(obj.is_active)
        self.assertTrue(Company.objects.get(pk=self.folder.company_id).is_active)

    def test_archive_without_htmx_redirects_to_the_folder(self):
        """A classic POST redirects to the folder page."""
        response = self.client.post(self.archive_url)
        self.assertRedirects(
            response, reverse("inspections:folder_detail", args=[self.folder.pk])
        )

    def test_unarchive_restores_the_tree(self):
        """Unarchiving restores the folder and what was archived with it."""
        self.folder.archive(self.owner)
        response = self.htmx_post(self.unarchive_url)
        self.assertEqual(response["HX-Refresh"], "true")
        for obj in (self.folder, self.visit, self.rec, self.media):
            obj.refresh_from_db()
            self.assertTrue(obj.is_active)

    def test_delete_get_on_an_active_folder_is_blocked(self):
        """The delete modal of an active folder has a blocking message, no confirm button."""
        response = self.htmx_get(self.delete_url)
        self.assertModal(response, blocking=True)
        self.assertIn("pas archivé", response.context["blocking"]["title"])

    def test_delete_get_on_an_archived_folder_offers_the_confirmation(self):
        """The delete modal of an archived folder lists what goes away and can be confirmed."""
        self.folder.archive(self.owner)
        response = self.htmx_get(self.delete_url)
        self.assertModal(response, blocking=False)
        self.assertTrue(response.context["danger"])
        self.assertEqual(response.context["confirm_label"], "Supprimer définitivement")
        self.assertIn("1 média", response.context["sections"][0]["entries"][2])

    def test_delete_post_on_an_active_folder_is_409(self):
        """An active folder cannot be deleted."""
        response = self.htmx_post(self.delete_url)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(InspectionFolder.objects.filter(pk=self.folder.pk).exists())

    def test_delete_post_on_an_archived_folder_redirects_to_the_list(self):
        """Deleting an archived folder removes it with its children and goes to the list."""
        self.folder.archive(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.htmx_post(self.delete_url)
        self.assertEqual(response["HX-Redirect"], reverse("inspections:folder_list"))
        self.assertFalse(InspectionFolder.objects.exists())
        self.assertFalse(VisitInstance.objects.exists())
        self.assertFalse(Recommandation.objects.exists())

    def test_delete_without_htmx_redirects(self):
        """A classic POST redirects to the list."""
        self.folder.archive(self.owner)
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, reverse("inspections:folder_list"))


class CompanyArchiveDeleteTests(ModalAssertionsMixin, HtmxClientMixin, TestCase):
    """``company_archive``, ``company_unarchive`` and ``company_delete``."""

    def setUp(self):
        """Create a client with a free contact."""
        super().setUp()
        self.company = CompanyFactory(created_by=self.owner)
        self.contact = ContactFactory(
            company=self.company, first_name="Ada", last_name="Free"
        )
        self.archive_url = reverse("crm:company_archive", args=[self.company.pk])
        self.delete_url = reverse("crm:company_delete", args=[self.company.pk])

    def test_archive_get_lists_the_contacts_that_follow(self):
        """The modal lists the contacts archived with the client."""
        response = self.htmx_get(self.archive_url)
        self.assertModal(response, blocking=False)
        self.assertEqual(response.context["sections"][0]["entries"], ["Ada Free"])

    def test_archive_get_warns_about_active_folders_and_kept_contacts(self):
        """Contacts used by an active folder stay active, folders are listed as warnings."""
        folder = InspectionFolderFactory(company=self.company, created_by=self.owner)
        response = self.htmx_get(self.archive_url)
        sections = response.context["sections"]
        self.assertTrue(any(folder.reference in s.get("entries", []) for s in sections))
        kept = [
            s
            for s in sections
            if folder.contact.first_name in " ".join(s.get("entries", []))
        ]
        self.assertTrue(kept)
        self.assertTrue(all(s["warning"] for s in kept))

    def test_archive_post_refreshes_and_archives_the_contacts(self):
        """POST archives the client and its free contacts."""
        response = self.htmx_post(self.archive_url)
        self.assertEqual(response["HX-Refresh"], "true")
        self.company.refresh_from_db()
        self.contact.refresh_from_db()
        self.assertFalse(self.company.is_active)
        self.assertFalse(self.contact.is_active)

    def test_unarchive_leaves_the_contacts_archived(self):
        """Unarchiving the client does not reactivate its contacts."""
        self.company.archive(self.owner)
        response = self.htmx_post(
            reverse("crm:company_unarchive", args=[self.company.pk])
        )
        self.assertEqual(response["HX-Refresh"], "true")
        self.company.refresh_from_db()
        self.contact.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertFalse(self.contact.is_active)

    def test_delete_of_an_active_client_is_blocked(self):
        """GET shows a blocking message and POST answers 409."""
        self.assertModal(self.htmx_get(self.delete_url), blocking=True)
        self.assertEqual(self.htmx_post(self.delete_url).status_code, 409)
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_delete_of_a_client_with_folders_is_blocked_even_when_archived(self):
        """A client with a folder, even archived, cannot be deleted: blocking list of folders."""
        folder = InspectionFolderFactory(
            company=self.company, created_by=self.owner, archived=True
        )
        self.company.archive(self.owner)
        response = self.htmx_get(self.delete_url)
        self.assertModal(response, blocking=True)
        self.assertEqual(response.context["blocking"]["entries"], [folder.reference])
        self.assertEqual(self.htmx_post(self.delete_url).status_code, 409)
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_delete_of_an_archived_client_removes_it_with_its_contacts(self):
        """An archived client without folder is deleted with its contacts."""
        self.company.archive(self.owner)
        response = self.htmx_get(self.delete_url)
        self.assertModal(response, blocking=False)
        self.assertIn(
            "1 contact sera supprimé", response.context["sections"][0]["title"]
        )
        response = self.htmx_post(self.delete_url)
        self.assertEqual(response["HX-Redirect"], reverse("crm:company_list"))
        self.assertFalse(Company.objects.filter(pk=self.company.pk).exists())
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_delete_without_htmx_redirects(self):
        """A classic POST redirects to the list."""
        self.company.archive(self.owner)
        self.assertRedirects(
            self.client.post(self.delete_url), reverse("crm:company_list")
        )


class ContactArchiveDeleteTests(ModalAssertionsMixin, HtmxClientMixin, TestCase):
    """``contact_archive``, ``contact_unarchive`` and ``contact_delete``."""

    def setUp(self):
        """Create a contact used by an active folder and a free one."""
        super().setUp()
        self.folder = InspectionFolderFactory(created_by=self.owner)
        self.used = self.folder.contact
        self.free = ContactFactory(company=self.folder.company)

    def url(self, name, contact):
        """Reverse a ``crm`` URL for a contact.

        Args:
            name: URL name without namespace.
            contact: Contact in the URL.

        Returns:
            The URL.
        """
        return reverse(f"crm:{name}", args=[contact.pk])

    def test_archive_of_a_free_contact(self):
        """GET offers the confirmation, POST archives and refreshes."""
        self.assertModal(
            self.htmx_get(self.url("contact_archive", self.free)), blocking=False
        )
        response = self.htmx_post(self.url("contact_archive", self.free))
        self.assertEqual(response["HX-Refresh"], "true")
        self.free.refresh_from_db()
        self.assertFalse(self.free.is_active)
        self.assertEqual(self.free.archived_by, self.owner)

    def test_archive_of_a_contact_of_an_active_folder_is_refused(self):
        """The modal is blocking, the POST answers 409 and nothing changes."""
        response = self.htmx_get(self.url("contact_archive", self.used))
        self.assertModal(response, blocking=True)
        self.assertEqual(
            response.context["blocking"]["entries"], [self.folder.reference]
        )
        self.assertEqual(
            self.htmx_post(self.url("contact_archive", self.used)).status_code, 409
        )
        self.used.refresh_from_db()
        self.assertTrue(self.used.is_active)

    def test_archive_is_possible_once_the_folder_is_archived(self):
        """An archived folder no longer blocks the archiving of its contact."""
        self.folder.archive(self.owner)
        response = self.htmx_post(self.url("contact_archive", self.used))
        self.assertEqual(response["HX-Refresh"], "true")

    def test_unarchive(self):
        """Unarchiving restores the contact."""
        self.free.archive(self.owner)
        response = self.htmx_post(self.url("contact_unarchive", self.free))
        self.assertEqual(response["HX-Refresh"], "true")
        self.free.refresh_from_db()
        self.assertTrue(self.free.is_active)

    def test_delete_of_an_active_contact_is_blocked(self):
        """An active contact cannot be deleted."""
        self.assertModal(
            self.htmx_get(self.url("contact_delete", self.free)), blocking=True
        )
        self.assertEqual(
            self.htmx_post(self.url("contact_delete", self.free)).status_code, 409
        )

    def test_delete_of_a_contact_referenced_by_a_folder_is_blocked(self):
        """A contact referenced by a folder, even an archived one, cannot be deleted."""
        self.folder.archive(self.owner)
        self.used.archive(self.owner)
        response = self.htmx_get(self.url("contact_delete", self.used))
        self.assertModal(response, blocking=True)
        self.assertEqual(
            self.htmx_post(self.url("contact_delete", self.used)).status_code, 409
        )
        self.assertTrue(Contact.objects.filter(pk=self.used.pk).exists())

    def test_delete_of_an_archived_free_contact(self):
        """An archived contact without folder is deleted and the list is shown."""
        self.free.archive(self.owner)
        self.assertModal(
            self.htmx_get(self.url("contact_delete", self.free)), blocking=False
        )
        response = self.htmx_post(self.url("contact_delete", self.free))
        self.assertEqual(response["HX-Redirect"], reverse("crm:contact_list"))
        self.assertFalse(Contact.objects.filter(pk=self.free.pk).exists())


class VisitArchiveDeleteTests(ModalAssertionsMixin, HtmxClientMixin, TestCase):
    """Visit archiving and deletion re-render the visits tab."""

    def setUp(self):
        """Create a visit with a media attached."""
        super().setUp()
        self.visit = VisitInstanceFactory(
            created_by=self.owner, folder__created_by=self.owner
        )
        self.folder = self.visit.folder
        self.media = MediaFactory(
            folder=self.folder, created_by=self.owner, visit=self.visit
        )

    def url(self, name):
        """Reverse an ``inspections`` URL for the visit.

        Args:
            name: URL name without namespace.

        Returns:
            The URL.
        """
        return reverse(f"inspections:{name}", args=[self.visit.pk])

    def test_archive_and_unarchive_return_the_tab(self):
        """Both actions answer with the visits tab and change the visit."""
        response = self.htmx_post(self.url("visit_archive"))
        self.assertTemplateUsed(response, VISIT_TAB)
        self.visit.refresh_from_db()
        self.assertFalse(self.visit.is_active)
        response = self.htmx_post(self.url("visit_unarchive"))
        self.assertTemplateUsed(response, VISIT_TAB)
        self.visit.refresh_from_db()
        self.assertTrue(self.visit.is_active)

    def test_archive_without_htmx_redirects_to_the_folder(self):
        """A classic POST redirects to the folder."""
        response = self.client.post(self.url("visit_archive"))
        self.assertRedirects(
            response, reverse("inspections:folder_detail", args=[self.folder.pk])
        )

    def test_delete_modal_targets_the_tab_and_announces_the_kept_medias(self):
        """The modal posts to the tab and says the medias stay on the folder."""
        self.visit.archive(self.owner)
        response = self.htmx_get(self.url("visit_delete"))
        self.assertModal(response, blocking=False)
        self.assertEqual(response.context["post_target"], "#tab-content")
        self.assertEqual(
            response.context["sections"][0]["entries"],
            ["1 média rattaché conservé dans le dossier"],
        )

    def test_delete_of_an_active_visit_is_blocked(self):
        """An active visit cannot be deleted."""
        self.assertModal(self.htmx_get(self.url("visit_delete")), blocking=True)
        self.assertEqual(self.htmx_post(self.url("visit_delete")).status_code, 409)

    def test_delete_of_an_archived_visit_returns_the_tab_and_keeps_the_media(self):
        """The visit goes away, its media stays on the folder."""
        self.visit.archive(self.owner)
        response = self.htmx_post(self.url("visit_delete"))
        self.assertTemplateUsed(response, VISIT_TAB)
        self.assertFalse(VisitInstance.objects.exists())
        self.media.refresh_from_db()
        self.assertIsNone(self.media.visit)

    def test_archived_tab_lists_archived_visits(self):
        """The tab re-rendered for ``status=archived`` shows the archived visits."""
        self.visit.archive(self.owner)
        response = self.htmx_get(
            reverse("inspections:folder_tab_visit", args=[self.folder.pk]),
            {"status": "archived"},
        )
        self.assertEqual(list(response.context["visits"]), [self.visit])


class RecommandationArchiveDeleteTests(ModalAssertionsMixin, HtmxClientMixin, TestCase):
    """Recommendation archiving and deletion re-render the recommendations tab."""

    def setUp(self):
        """Create a recommendation."""
        super().setUp()
        self.folder = InspectionFolderFactory(created_by=self.owner)
        self.rec = RecommandationFactory(folder=self.folder, created_by=self.owner)

    def url(self, name):
        """Reverse an ``inspections`` URL for the recommendation.

        Args:
            name: URL name without namespace.

        Returns:
            The URL.
        """
        return reverse(f"inspections:{name}", args=[self.rec.pk])

    def test_archive_and_unarchive_return_the_tab(self):
        """Both actions answer with the recommendations tab."""
        response = self.htmx_post(self.url("recommandation_archive"))
        self.assertTemplateUsed(response, REC_TAB)
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_active)
        response = self.htmx_post(self.url("recommandation_unarchive"))
        self.assertTemplateUsed(response, REC_TAB)
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.is_active)

    def test_delete_rules(self):
        """Active: blocked (modal and 409). Archived: confirmation, then the tab."""
        url = self.url("recommandation_delete")
        self.assertModal(self.htmx_get(url), blocking=True)
        self.assertEqual(self.htmx_post(url).status_code, 409)
        self.rec.archive(self.owner)
        response = self.htmx_get(url)
        self.assertModal(response, blocking=False)
        self.assertEqual(response.context["object_label"], f"REC-{self.rec.pk}")
        response = self.htmx_post(url)
        self.assertTemplateUsed(response, REC_TAB)
        self.assertFalse(Recommandation.objects.exists())

    def test_delete_without_htmx_redirects_to_the_folder(self):
        """A classic POST redirects to the folder."""
        self.rec.archive(self.owner)
        response = self.client.post(self.url("recommandation_delete"))
        self.assertRedirects(
            response, reverse("inspections:folder_detail", args=[self.folder.pk])
        )


class TrackingBannerTests(HtmxClientMixin, TestCase):
    """The ``tracking_info`` banner of the folder, client and contact pages."""

    def setUp(self):
        """Create a folder (client and contact included)."""
        super().setUp()
        self.owner.first_name, self.owner.last_name = "Nina", "Archiviste"
        self.owner.save()
        self.folder = InspectionFolderFactory(created_by=self.owner)
        self.pages = [
            (
                "folder",
                self.folder,
                reverse("inspections:folder_tab_overview", args=[self.folder.pk]),
            ),
            (
                "company",
                self.folder.company,
                reverse("crm:company_detail", args=[self.folder.company_id]),
            ),
            (
                "contact",
                self.folder.contact,
                reverse("crm:contact_detail", args=[self.folder.contact_id]),
            ),
        ]

    def test_active_objects_show_no_archive_line(self):
        """While an object is active the banner has no "Archivé le" line."""
        for name, _, url in self.pages:
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertContains(response, "Créé le")
                self.assertNotContains(response, "Archivé le")

    def test_archived_objects_show_who_archived_them(self):
        """Once archived, the banner says "Archivé le … par …"."""
        for name, obj, url in self.pages:
            obj.archive(self.owner)
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertContains(response, "Archivé le")
                self.assertContains(response, "Nina Archiviste")
                self.assertContains(response, obj.archived_at.strftime("%d/%m/%Y"))

    def test_banner_disappears_after_unarchiving(self):
        """The archive line goes away when the object is restored."""
        self.folder.archive(self.owner)
        self.folder.unarchive(self.owner)
        response = self.client.get(self.pages[0][2])
        self.assertNotContains(response, "Archivé le")
