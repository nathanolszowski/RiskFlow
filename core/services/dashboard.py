import math

from django.db.models import Count, Q
from django.utils import timezone

from inspections.models import InspectionFolder, VisitInstance
from inspections.services.inspectionfolder import get_inspection_folders_by_user

MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
WEEKDAYS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MONTHS_SHORT_FR = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]

# Phases counted as "en cours" (COMPLETED and ARCHIVED are out), with their chart color token.
ONGOING_PHASES = [
    (InspectionFolder.Phase.CREATION, "var(--chart-1)"),
    (InspectionFolder.Phase.IN_PROGRESS, "var(--chart-2)"),
    (InspectionFolder.Phase.REVIEW, "var(--chart-3)"),
]

UPCOMING_VISITS_LIMIT = 4
DONUT_RADIUS = 76
DONUT_GAP = 3


def parse_period(month_raw, year_raw, today=None):
    """
    Return a valid (month, year) from raw GET values, falling back to the current month/year.
    """
    today = today or timezone.localdate()
    try:
        month = int(month_raw)
        if not 1 <= month <= 12:
            raise ValueError
    except (TypeError, ValueError):
        month = today.month
    try:
        year = int(year_raw)
        if not today.year - 2 <= year <= today.year:
            raise ValueError
    except (TypeError, ValueError):
        year = today.year
    return month, year


def _previous_period(month, year):
    return (12, year - 1) if month == 1 else (month - 1, year)


def _ongoing_folders(user, month, year):
    """
    Folders of the user still in progress that were modified during the given month.
    """
    return get_inspection_folders_by_user(user).filter(
        current_phase__in=[phase for phase, _ in ONGOING_PHASES],
        updated_at__year=year,
        updated_at__month=month,
    )


def _phase_breakdown(folders):
    """
    Count the folders per ongoing phase, with the SVG donut geometry (stroke-dasharray/offset) of each slice.
    """
    counts = dict(
        folders.order_by().values_list("current_phase").annotate(total=Count("pk"))
    )
    total = sum(counts.values())
    circumference = 2 * math.pi * DONUT_RADIUS
    phases, offset = [], 0.0
    for phase, color in ONGOING_PHASES:
        count = counts.get(phase.value, 0)
        length = (count / total) * circumference if total else 0
        phases.append({
            "label": phase.label,
            "count": count,
            "pct": round(count / total * 100) if total else 0,
            "color": color,
            "dash": f"{max(length - DONUT_GAP, 0):.2f} {circumference:.2f}",
            "offset": f"{-offset:.2f}",
        })
        offset += length
    return phases


def get_upcoming_visits(user, today=None):
    """
    The next visits of the user: planned from today on, plus any overdue one, ordered by date.
    """
    today = today or timezone.localdate()
    visits = (
        VisitInstance.objects.filter(
            folder__created_by=user,
            folder__is_active=True,
            is_active=True,
            due_date__isnull=False,
        )
        .filter(Q(due_date__gte=today) | Q(current_status=VisitInstance.Status.DELAY))
        .select_related("folder__company")
        .order_by("due_date", "pk")[:UPCOMING_VISITS_LIMIT]
    )
    return [
        {
            "visit": visit,
            "weekday": WEEKDAYS_FR[visit.due_date.weekday()],
            "month_short": MONTHS_SHORT_FR[visit.due_date.month - 1],
        }
        for visit in visits
    ]


def get_dashboard_context(user, month=None, year=None, today=None):
    """
    Build the dashboard data for a user.
    The month/year filter applies to the ongoing-folders KPI and the status chart;
    the last modified folder and the upcoming visits are always current.
    """
    today = today or timezone.localdate()
    month = month or today.month
    year = year or today.year

    phases = _phase_breakdown(_ongoing_folders(user, month, year))
    total = sum(p["count"] for p in phases)

    prev_month, prev_year = _previous_period(month, year)
    previous_total = _ongoing_folders(user, prev_month, prev_year).count()

    return {
        "month": month,
        "year": year,
        "months": list(enumerate(MONTHS_FR, start=1)),
        "years": list(range(today.year - 2, today.year + 1)),
        "period_label": f"{MONTHS_FR[month - 1]} {year}",
        "previous_period_label": f"{MONTHS_FR[prev_month - 1].lower()} {prev_year}",
        "ongoing_total": total,
        "ongoing_delta": total - previous_total,
        "phases": phases,
        "last_folder": get_inspection_folders_by_user(user).order_by("-updated_at").first(),
        "upcoming_visits": get_upcoming_visits(user, today),
    }
