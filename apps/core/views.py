"""Core views: dashboard, session heartbeat, theme toggle and global search."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from django_htmx.middleware import HtmxDetails

from core.decorators import htmx_login_required, logged_user
from core.htmx import htmx_refresh
from core.services.dashboard import get_dashboard_context, parse_period
from core.services.geo import suggest
from core.services.search import global_search as global_search_service


class HtmxHttpRequest(HttpRequest):
    """Typing helper: ``HttpRequest`` with the ``htmx`` attribute added by django-htmx."""

    htmx: HtmxDetails


@htmx_login_required
@require_GET
def dashboard(request: HtmxHttpRequest) -> HttpResponse:
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
    context = get_dashboard_context(logged_user(request), month, year)
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


@require_POST
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
        return htmx_refresh()

    referer = request.META.get("HTTP_REFERER", "")
    if not url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        referer = "/"
    return redirect(referer)


@htmx_login_required
@require_GET
def global_search(request: HttpRequest) -> HttpResponse:
    """Search folders, companies and contacts matching the ``q`` GET parameter.

    See ``core.services.search.global_search``: from two characters, at most five
    results per category, folders of the user only, every client and contact.

    Args:
        request: Current request.

    Returns:
        The search results partial.
    """
    query = request.GET.get("q", "").strip()
    results = global_search_service(logged_user(request), query)

    return render(
        request,
        "core/partials/search/search_results.html",
        {"query": query, **results},
    )


@htmx_login_required
@require_GET
def address_suggestions(request: HttpRequest) -> HttpResponse:
    """Suggest addresses for the street being typed (HTMX).

    Args:
        request: Current request. ``address_line`` (or ``origin_address`` for a
            starting point) holds the text typed so far.

    Returns:
        The suggestions partial, empty when the text is too short or the geocoding
        service is unavailable.
    """
    text = request.GET.get("address_line") or request.GET.get("origin_address", "")
    suggestions = suggest(text)
    return render(
        request,
        "core/partials/ui/address_suggestions.html",
        {"suggestions": suggestions},
    )
