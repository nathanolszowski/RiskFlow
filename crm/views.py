from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)
from django.core.paginator import Paginator

from crm.services.company import INSEEApiClient, get_filtered_companies
from crm.services.contact import get_filtered_contacts

from .forms import CompanyForm, ContactForm
from .models import Company, Contact


# ==========================================
# ==== COMPANY SECTION =====================
# ==========================================


@login_required
@require_GET
def company_list(request):
    """Render companies list view."""
    companies = get_filtered_companies(request)

    paginator = Paginator(companies, 15)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "crm/company.html",
        {
            "companies": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def company_list_paginated(request, page=1):
    """Render companies list view with update page."""
    companies = get_filtered_companies(request)

    paginator = Paginator(companies, 15)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "crm/partials/company_grid.html",
        {
            "companies": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def company_detail(request, pk):
    """Render main view for company detail data."""
    company = get_object_or_404(Company, pk=pk)

    context = {
        "company": company,
    }
    return render(request, "crm/company_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_company(request):
    """HTMX modal view to render the creation window for companies."""
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save(commit=False)
            company.created_by = request.user
            company.save()

            companies = get_filtered_companies(request)
            paginator = Paginator(companies, 15)
            page_obj = paginator.get_page(1)

            response = render(
                request,
                "crm/partials/company_grid.html",
                {"companies": page_obj, "page_obj": page_obj},
            )
            response["HX-Trigger"] = "closeModal"
            return response
        else:
            return render(
                request,
                "crm/partials/company_form_modal.html",
                {"form": form},
                status=422,
            )

    form = CompanyForm()
    return render(
        request, "crm/partials/company_form_modal.html", {"form": form}
    )


@login_required
@require_http_methods(["GET", "POST"])
def company_inline_update(request, pk):
    """
    HTMX modal view to edit company data.
    - GET  : Render auto-complete form (company_update.html).
    - POST : Update validation.
             If True -> Render read view with data (company_read.html).
             If False -> Render form with errors (company_update.html).
    """
    company = get_object_or_404(Company, pk=pk)

    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            return render(
                request,
                "crm/partials/company_read.html",
                {"company": company},
            )
    else:
        form = CompanyForm(instance=company)

    return render(
        request,
        "crm/partials/company_update.html",
        {"company": company, "form": form},
    )


@login_required
@require_GET
def company_inline_read(request, pk):
    """
    HTMX view to read only company view from detail view.
    Only fragment (company_read.html).
    """
    company = get_object_or_404(Company, pk=pk)
    return render(
        request,
        "crm/partials/company_read.html",
        {"company": company},
    )

@require_POST
def company_archive(request, pk):
    company = get_object_or_404(Company, pk=pk)
    company.is_active = False
    
    # Si vous suivez la traçabilité de l'utilisateur
    if hasattr(company, 'updated_by'):
        company.updated_by = request.user
        
    company.save()

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=200)
        response["HX-Redirect"] = request.META.get("HTTP_REFERER", f"/crm/companies/{company.pk}/")
        return response

    return redirect("crm:company_detail", pk=company.pk)


@require_POST
def company_unarchive(request, pk):
    company = get_object_or_404(Company, pk=pk)
    company.is_active = True
    
    # Si vous suivez la traçabilité de l'utilisateur
    if hasattr(company, 'updated_by'):
        company.updated_by = request.user
        
    company.save()

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=200)
        response["HX-Redirect"] = request.META.get("HTTP_REFERER", f"/crm/companies/{company.pk}/")
        return response

    return redirect("crm:company_detail", pk=company.pk)

@login_required
@require_GET
def search_siret_api(request):
    """Request data from INSEE API and auto-complete the company creation form"""
    siret_query = (
        request.GET.get("siret_search", "")
        .strip()
        .replace(" ", "")
        .replace("-", "")
    )

    if not siret_query or len(siret_query) != 14 or not siret_query.isdigit():
        return HttpResponse("")

    company_data = INSEEApiClient.fetch_by_siret(siret_query)

    if company_data:
        context = {"found": True, **company_data}
    else:
        context = {"found": False, "query": siret_query}

    return render(request, "crm/partials/siret_search_result.html", context)


# ==========================================
# ==== CONTACT SECTION =====================
# ==========================================


@login_required
@require_GET
def contact_list(request):
    """Render contacts list view"""
    companies = Company.objects.all().order_by("name")
    contacts = get_filtered_contacts(request)

    paginator = Paginator(contacts, 15)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "crm/contact.html",
        {
            "contacts": page_obj,
            "page_obj": page_obj,
            "companies": companies,
        },
    )


@login_required
@require_GET
def contact_list_paginated(request, page=1):
    """Render contacts list view with update page"""
    contacts = get_filtered_contacts(request)

    paginator = Paginator(contacts, 15)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "crm/partials/contact_grid.html",
        {
            "contacts": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
@require_GET
def contact_detail(request, pk):
    """Render the detail view for a contact"""
    contact = get_object_or_404(
        Contact.objects.select_related("company"), pk=pk
    )
    return render(request, "crm/contact_detail.html", {"contact": contact})


@login_required
@require_http_methods(["GET", "POST"])
def create_contact(request):
    """HTMX view to render and process the creation form for contacts."""
    # Retrieve company_id from query parameters (GET) or form submission (POST)
    company_id = request.GET.get("company") or request.POST.get("company")

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.created_by = request.user
            contact.save()

            # If created from a company detail page, refresh the page to show the new contact
            if company_id:
                response = HttpResponse(status=204)
                response["HX-Refresh"] = "true"
                return response
            # Default behavior for global contact list view
            contacts = get_filtered_contacts(request)
            paginator = Paginator(contacts, 15)
            page_obj = paginator.get_page(1)

            response = render(
                request,
                "crm/partials/contact_grid.html",
                {"contacts": page_obj, "page_obj": page_obj},
            )
            response["HX-Trigger"] = "closeModal"
            return response
        else:
            return render(
                request,
                "crm/partials/contact_form_modal.html",
                {"form": form},
                status=422,
            )
    # Pre-fill company initial data for GET request
    initial_data = {}
    if company_id:
        initial_data["company"] = company_id

    form = ContactForm(initial=initial_data)
    return render(
        request, "crm/partials/contact_form_modal.html", {"form": form}
    )