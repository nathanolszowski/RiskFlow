"""Core views: dashboard, session heartbeat, theme toggle and global search."""

from crm.models import Company, Contact
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET
from inspections.models import InspectionFolder

from core.decorators import htmx_login_required
from core.services.dashboard import get_dashboard_context, parse_period


@htmx_login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    """Render the dashboard of the logged-in user.

    The ``month`` and ``year`` GET parameters filter the period (invalid values
    fall back to the current one). On an HTMX request only the content partial
    is returned.

    Args:
        request: Current request.

    Returns:
        The full page or the dashboard content partial.
    """
    month, year = parse_period(request.GET.get("month"), request.GET.get("year"))
    context = get_dashboard_context(request.user, month, year)
    context["today"] = timezone.localdate()
    template = (
        "core/partials/dashboard/dashboard_content.html"
        if request.htmx
        else "core/dashboard.html"
    )
    return render(request, template, context)


@htmx_login_required(redirect=False)
@require_GET
def session_ping(request: HttpRequest) -> HttpResponse:
    """Heartbeat that keeps the session alive.

    ``SESSION_SAVE_EVERY_REQUEST`` restarts the session countdown on each call.
    Answers 401 without redirect when the session has expired.

    Args:
        request: Current request.

    Returns:
        An empty 204 response.
    """
    return HttpResponse(status=204)


def toggle_theme(request: HttpRequest) -> HttpResponse:
    """Switch the theme stored in the session between dark and light.

    Args:
        request: Current request.

    Returns:
        A response with ``HX-Refresh`` on an HTMX request, otherwise a redirect to
        the referring page.
    """
    current_theme = request.session.get("theme", "dark")
    new_theme = "light" if current_theme == "dark" else "dark"
    request.session["theme"] = new_theme
    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    return redirect(request.META.get("HTTP_REFERER", "/"))


@htmx_login_required
def global_search(request: HttpRequest) -> HttpResponse:
    """Search folders, companies and contacts matching the ``q`` GET parameter.

    The search starts at two characters and returns at most five results per
    category. Folders are searched among the ones of the user; clients and contacts
    are shared between users, so all of them are searched.

    Args:
        request: Current request.

    Returns:
        The search results partial.
    """
    query = request.GET.get("q", "").strip()
    folders = []
    companies = []
    contacts = []

    if query and len(query) >= 2:
        folders = InspectionFolder.objects.filter(
            Q(reference__icontains=query) | Q(company__name__icontains=query),
            created_by=request.user,
        )[:5]

        companies = Company.objects.filter(
            Q(name__icontains=query) | Q(address__icontains=query)
        )[:5]

        contacts = Contact.objects.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )[:5]

    return render(
        request,
        "core/partials/search/search_results.html",
        {
            "query": query,
            "folders": folders,
            "companies": companies,
            "contacts": contacts,
        },
    )
