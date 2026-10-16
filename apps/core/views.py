from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.shortcuts import redirect
from django.db.models import Q
from inspections.models import InspectionFolder
from crm.models import Company, Contact
from core.services.dashboard import get_dashboard_context, parse_period
from core.decorators import htmx_login_required


@login_required
@require_GET
def dashboard(request):
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
def session_ping(request):
    """Heartbeat: SESSION_SAVE_EVERY_REQUEST restarts the session countdown on each call."""
    return HttpResponse(status=204)


def toggle_theme(request):
    current_theme = request.session.get("theme", "dark")
    new_theme = "light" if current_theme == "dark" else "dark"
    request.session["theme"] = new_theme
    if request.headers.get("HX-Request"):
        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    return redirect(request.META.get("HTTP_REFERER", "/"))


def global_search(request):
    query = request.GET.get("q", "").strip()
    folders = []
    companies = []
    contacts = []

    if query and len(query) >= 2:
        folders = InspectionFolder.objects.filter(
            Q(reference__icontains=query) | Q(company__name__icontains=query)
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
