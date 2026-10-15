from datetime import date, datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services.dashboard import get_dashboard_context, get_upcoming_visits, parse_period
from crm.models import Company
from inspections.models import InspectionFolder, VisitInstance, VisitTemplate

User = get_user_model()
TODAY = date(2026, 10, 15)


class DashboardServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("inspector", password="pw")
        cls.other = User.objects.create_user("other", password="pw")
        cls.template = VisitTemplate.objects.create(name="Standard", created_by=cls.user)
        cls.counter = 0

    def make_company(self, user):
        self.counter += 1
        n = self.counter
        return Company.objects.create(
            reference=f"C{n}", name=f"Client {n}", address="1 rue Test", siret=f"{n:014d}",
            business_line="Industrie", siren=f"{n:09d}", company_size_category="PME",
            nb_employees=10, creation_date=date(2000, 1, 1), created_by=user,
        )

    def make_folder(self, user=None, phase=InspectionFolder.Phase.IN_PROGRESS, updated=None, **kwargs):
        user = user or self.user
        folder = InspectionFolder.objects.create(
            company=self.make_company(user), current_phase=phase, created_by=user, **kwargs
        )
        if updated:
            InspectionFolder.objects.filter(pk=folder.pk).update(updated_at=updated)
        return folder

    def make_visit(self, folder, due_date, status=VisitInstance.Status.SCHEDULED, **kwargs):
        return VisitInstance.objects.create(
            folder=folder, template=self.template, due_date=due_date,
            current_status=status, created_by=folder.created_by, **kwargs,
        )

    def test_parse_period_falls_back_on_invalid_values(self):
        self.assertEqual(parse_period("13", "abc", today=TODAY), (10, 2026))
        self.assertEqual(parse_period("3", "1999", today=TODAY), (3, 2026))
        self.assertEqual(parse_period("3", "2025", today=TODAY), (3, 2025))

    def test_ongoing_count_is_scoped_to_user_phase_and_period(self):
        in_october = datetime(2026, 10, 5, tzinfo=dt_timezone.utc)
        self.make_folder(updated=in_october)
        self.make_folder(phase=InspectionFolder.Phase.REVIEW, updated=in_october)
        self.make_folder(phase=InspectionFolder.Phase.COMPLETED, updated=in_october)
        self.make_folder(user=self.other, updated=in_october)
        self.make_folder(updated=datetime(2026, 9, 5, tzinfo=dt_timezone.utc))
        archived = self.make_folder(updated=in_october)
        archived.archive(self.user)
        InspectionFolder.objects.filter(pk=archived.pk).update(updated_at=in_october)

        ctx = get_dashboard_context(self.user, 10, 2026, today=TODAY)

        self.assertEqual(ctx["ongoing_total"], 2)
        self.assertEqual(ctx["ongoing_delta"], 1)
        counts = {p["label"]: p["count"] for p in ctx["phases"]}
        self.assertEqual(counts["Dossier en cours"], 1)
        self.assertEqual(counts["En cours de revue"], 1)
        self.assertEqual(counts["En création"], 0)

    def test_empty_dashboard(self):
        ctx = get_dashboard_context(self.user, 10, 2026, today=TODAY)
        self.assertEqual(ctx["ongoing_total"], 0)
        self.assertIsNone(ctx["last_folder"])
        self.assertEqual(ctx["upcoming_visits"], [])

    def test_last_folder_is_most_recently_updated_of_the_user(self):
        self.make_folder(updated=datetime(2026, 1, 1, tzinfo=dt_timezone.utc))
        recent = self.make_folder(updated=datetime(2026, 6, 1, tzinfo=dt_timezone.utc))
        self.make_folder(user=self.other)  # more recent but not owned
        ctx = get_dashboard_context(self.user, 10, 2026, today=TODAY)
        self.assertEqual(ctx["last_folder"], recent)

    def test_upcoming_visits_limit_order_and_filters(self):
        folder = self.make_folder()
        foreign = self.make_folder(user=self.other)
        self.make_visit(foreign, date(2026, 10, 16))
        self.make_visit(folder, date(2026, 10, 1))  # past and not overdue-flagged: excluded
        late = self.make_visit(folder, date(2026, 10, 10), VisitInstance.Status.DELAY)
        for day in (22, 16, 20, 18, 25):
            self.make_visit(folder, date(2026, 10, day))
        archived = self.make_visit(folder, date(2026, 10, 15))
        archived.archive(self.user)

        visits = get_upcoming_visits(self.user, TODAY)

        self.assertEqual(len(visits), 4)
        self.assertEqual(visits[0]["visit"], late)
        self.assertEqual(
            [v["visit"].due_date.day for v in visits], [10, 16, 18, 20]
        )
        self.assertEqual(visits[0]["month_short"], "oct.")

    def test_donut_slices_cover_the_circle(self):
        in_october = datetime(2026, 10, 5, tzinfo=dt_timezone.utc)
        for phase in (InspectionFolder.Phase.CREATION, InspectionFolder.Phase.IN_PROGRESS):
            self.make_folder(phase=phase, updated=in_october)
        ctx = get_dashboard_context(self.user, 10, 2026, today=TODAY)
        self.assertEqual(sum(p["pct"] for p in ctx["phases"]), 100)


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("inspector", password="pw")

    def test_requires_login(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_full_page_and_htmx_partial(self):
        self.client.force_login(self.user)
        full = self.client.get(reverse("core:dashboard"), {"month": "3", "year": "2026"})
        self.assertEqual(full.status_code, 200)
        self.assertTemplateUsed(full, "core/dashboard.html")
        self.assertContains(full, "Mars 2026")

        partial = self.client.get(reverse("core:dashboard"), HTTP_HX_REQUEST="true")
        self.assertEqual(partial.status_code, 200)
        self.assertTemplateNotUsed(partial, "core/dashboard.html")
        self.assertTemplateUsed(partial, "core/partials/dashboard_content.html")
