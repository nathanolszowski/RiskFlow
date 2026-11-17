"""Tests for the shared layout (``core/base.html``): modal closing and theme tokens."""

import re
from pathlib import Path

from crm.tests.factories import CompanyFactory
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from inspections.tests.factories import InspectionFolderFactory, VisitInstanceFactory
from medias.tests.factories import MediaFactory
from medias.tests.helpers import TempMediaRootMixin

from core.tests.helpers import HtmxClientMixin

LISTENER = 'addEventListener("closeModal"'


class CloseModalTests(TempMediaRootMixin, HtmxClientMixin, TestCase):
    """``HX-Trigger: closeModal`` is handled once, by the layout."""

    def test_layout_listens_once_for_close_modal(self):
        """A full page registers a single ``closeModal`` listener."""
        response = self.client.get(reverse("crm:company_list"))
        self.assertEqual(response.content.decode().count(LISTENER), 1)

    def test_modals_register_no_listener_of_their_own(self):
        """A modal opened (or re-rendered) many times adds no ``closeModal`` listener."""
        company = CompanyFactory(created_by=self.owner)
        folder = InspectionFolderFactory(created_by=self.owner)
        visit = VisitInstanceFactory(folder=folder, created_by=self.owner)
        media = MediaFactory(folder=folder, created_by=self.owner)
        urls = [
            reverse("crm:create_company"),
            reverse("crm:create_contact"),
            reverse("inspections:create_folder"),
            reverse("inspections:visit_create", args=[folder.pk]),
            reverse("inspections:visit_update", args=[visit.pk]),
            reverse("medias:media_upload", args=[folder.pk]),
            reverse("medias:media_update", args=[media.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.htmx_get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "closeModal")
        page = self.client.get(reverse("crm:company_detail", args=[company.pk]))
        self.assertEqual(page.content.decode().count(LISTENER), 1)


class ThemeTokensTests(TestCase):
    """Templates use the theme tokens of ``styles.css``, not raw Tailwind colors."""

    def test_templates_use_no_raw_palette_color(self):
        """No template uses a raw Tailwind palette color (red-500, amber-400, black/70...)."""
        palette = (
            "red|rose|pink|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue"
            "|indigo|violet|purple|fuchsia|slate|gray|zinc|neutral|stone"
        )
        pattern = re.compile(
            rf"(?<![\w-])(?:bg|text|border|ring|accent|fill|stroke|from|to|via)-"
            rf"(?:(?:{palette})-\d{{2,3}}|black)(?:/\d+)?(?![\w-])"
        )
        apps = Path(settings.BASE_DIR) / "apps"
        offenders = [
            f"{path.relative_to(apps)}: {match.group()}"
            for path in apps.glob("*/templates/**/*.html")
            for match in pattern.finditer(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])
