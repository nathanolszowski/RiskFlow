from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from crm.services.company import INSEEApiClient, get_filtered_companies
from crm.services.contact import get_filtered_contacts

from .forms import CompanyForm, ContactForm
from .models import Company, Contact
from django.db.models import Count


"""

==== COMPANY SECTION ====

"""

@login_required
def company_list(request):
    """Render companies list view"""
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
def company_list_paginated(request, page=1):
    """Render companies list view with update page"""
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
def company_detail(request, pk):
    """Render the detail view for a company"""
    company = get_object_or_404(
        Company.objects.prefetch_related('inspection_folders'), 
        pk=pk
    )
    return render(request, 'crm/company_detail.html', {'company': company})


@login_required
def create_company(request):
    """HTMX view to render the creation window for companies"""
    if request.method == "POST":
            form = CompanyForm(request.POST)
            if form.is_valid():
                company = form.save(commit=False)
                company.created_by = request.user
                company.save()

                companies = get_filtered_companies(request)
                from django.core.paginator import Paginator
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
    return render(request, "crm/partials/company_form_modal.html", {"form": form})


@login_required
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

"""

==== CONTACT SECTION ====

"""

@login_required
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
def contact_list_paginated(request, page=1):
    """Render companies list view with update page"""
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
def contact_detail(request, pk):
    """Render the detail view for a company"""
    contact = get_object_or_404(
        Contact.objects.select_related("company"),
        pk=pk
    )
    return render(request, 'crm/contact_detail.html', {'contact': contact})

@login_required
def create_contact(request):
    """HTMX view to render the creation window for contacts"""
    if request.method == "POST":
            form = ContactForm(request.POST)
            if form.is_valid():
                contact = form.save(commit=False)
                contact.created_by = request.user
                contact.save()
                
                # Recharge de la liste pour HTMX...
                contacts = get_filtered_contacts(request)
                from django.core.paginator import Paginator
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

    form = ContactForm()
    return render(request, "crm/partials/contact_form_modal.html", {"form": form})