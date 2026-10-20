"""Data of the dashboard: ongoing folders per phase (donut chart) and upcoming visits."""

import math
from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Count, F, Q, QuerySet
from django.utils import timezone
from inspections.models import InspectionFolder, VisitInstance
from inspections.services.inspectionfolder import get_inspection_folders_by_user

if TYPE_CHECKING:
    from accounts.models import CustomUser

MONTHS_FR = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]
WEEKDAYS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MONTHS_SHORT_FR = [
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
]

# Phases counted as "en cours" (CLOSED and ARCHIVED are out), with their chart color token.
ONGOING_PHASES = [
    (InspectionFolder.Phase.CREATION, "var(--chart-1)"),
    (InspectionFolder.Phase.PREPARATION, "var(--chart-2)"),
    (InspectionFolder.Phase.VISIT, "var(--chart-3)"),
    (InspectionFolder.Phase.REPORT, "var(--chart-4)"),
    (InspectionFolder.Phase.FOLLOW_UP, "var(--chart-5)"),
]

UPCOMING_VISITS_LIMIT = 4
DONUT_RADIUS = 76
DONUT_GAP = 3


def parse_period(
    month_raw: Optional[str], year_raw: Optional[str], today: Optional[date] = None
) -> tuple[int, int]:
    """Return a valid ``(month, year)`` from raw GET values.

    Each invalid value falls back to the current month or year. The year must be
    within the last three years (current year included).

    Args:
        month_raw: Raw month value (1 to 12).
        year_raw: Raw year value.
        today: Reference date, the current local date by default.

    Returns:
        The month and the year.
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


def _previous_period(month: int, year: int) -> tuple[int, int]:
    """Return the ``(month, year)`` preceding the given one."""
    return (12, year - 1) if month == 1 else (month - 1, year)


def _ongoing_folders(user: "CustomUser", month: int, year: int) -> QuerySet:
    """Return the folders of the user still in progress and modified during the given month."""
    return get_inspection_folders_by_user(user).filter(
        current_phase__in=[phase for phase, _ in ONGOING_PHASES],
        updated_at__year=year,
        updated_at__month=month,
    )


def _phase_breakdown(folders: QuerySet) -> list[dict[str, Any]]:
    """Count the folders per ongoing phase, with the SVG donut geometry of each slice.

    Args:
        folders: Ongoing folders to count.

    Returns:
        One dict per phase of ``ONGOING_PHASES`` with ``label``, ``count``, ``pct``,
        ``color`` and the ``dash`` / ``offset`` values (stroke-dasharray and
        stroke-dashoffset) of its slice.
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
        phases.append(
            {
                "label": phase.label,
                "count": count,
                "pct": round(count / total * 100) if total else 0,
                "color": color,
                "dash": f"{max(length - DONUT_GAP, 0):.2f} {circumference:.2f}",
                "offset": f"{-offset:.2f}",
            }
        )
        offset += length
    return phases


def get_upcoming_visits(
    user: "CustomUser", today: Optional[date] = None
) -> list[dict[str, Any]]:
    """Return the next visits of the user, ordered by date.

    These are the active visits planned from today on, plus any overdue one, up to
    ``UPCOMING_VISITS_LIMIT``.

    Args:
        user: Owner of the folders.
        today: Reference date, the current local date by default.

    Returns:
        One dict per visit with ``visit``, ``weekday`` and ``month_short``.
    """
    today = today or timezone.localdate()
    visits = (
        VisitInstance.objects.filter(
            folder__created_by=user,
            folder__is_active=True,
            is_active=True,
            due_date__isnull=False,
        )
        .filter(
            Q(due_date__gte=today)
            | Q(current_status=VisitInstance.Status.DELAY)
            # A planned visit whose date is over is late, even if its status was never switched to DELAY
            | Q(current_status=VisitInstance.Status.SCHEDULED, due_date__lt=today)
        )
        .select_related("folder__company")
        .order_by("due_date", F("due_time").asc(nulls_last=True), "pk")[:UPCOMING_VISITS_LIMIT]
    )
    return [
        {
            "visit": visit,
            "weekday": WEEKDAYS_FR[visit.due_date.weekday()],
            "month_short": MONTHS_SHORT_FR[visit.due_date.month - 1],
        }
        for visit in visits
    ]


def get_dashboard_context(
    user: "CustomUser",
    month: Optional[int] = None,
    year: Optional[int] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Build the dashboard data for a user.

    The month/year filter applies to the ongoing-folders KPI and the status chart;
    the last modified folder and the upcoming visits are always current.

    Args:
        user: Owner of the folders.
        month: Month of the period, the current one by default.
        year: Year of the period, the current one by default.
        today: Reference date, the current local date by default.

    Returns:
        The template context: period and labels, ``ongoing_total`` and its delta
        with the previous month, ``phases``, ``last_folder`` and
        ``upcoming_visits``.
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
        "last_folder": get_inspection_folders_by_user(user)
        .order_by("-updated_at")
        .first(),
        "upcoming_visits": get_upcoming_visits(user, today),
    }
