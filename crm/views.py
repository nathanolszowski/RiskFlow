from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from crm.services.company import INSEEApiClient

from .forms import CompanyForm
from .models import Company, Contact
from django.db.models import Q, Count

@login_required
def company_list_view(request):
    companies = Company.objects.annotate(
        inspection_folders_count=Count('inspection_folders')
    )
    q = request.GET.get('q', '').strip()
    if q:
        companies = companies.filter(
            Q(name__icontains=q) | 
            Q(siren__icontains=q) | 
            Q(siret__icontains=q) | 
            Q(reference__icontains=q)
        )
    status = request.GET.get('status', 'active').strip()
    if status == 'active':
        companies = companies.filter(is_active=True)
    elif status == 'archived':
        companies = companies.filter(is_active=False)

    sort_by = request.GET.get('sort', 'name')
    allowed_sorts = ['name', '-created_at', '-inspection_folders_count']
    if sort_by in allowed_sorts:
        companies = companies.order_by(sort_by)

    if request.headers.get('HX-Request'):
        return render(request, 'crm/partials/company_grid.html', {'companies': companies})

    return render(request, 'crm/company.html', {'companies': companies})

@login_required
def company_detail_view(request, pk):

    company = get_object_or_404(
        Company.objects.prefetch_related('inspection_folders'), 
        pk=pk
    )
    return render(request, 'crm/company_detail.html', {'company': company})

@login_required
def create_company_htmx(request):
    """HTMX view for creating a new company via modal."""
    if request.method == 'POST':
        form = CompanyForm(request.POST)
        if form.is_valid():
            form.save()
            
            companies = Company.objects.all().order_by('-id')
            response = render(request, 'crm/partials/company_list.html', {'companies': companies})
            response['HX-Trigger'] = 'closeModal'
            return response
        else:
            return render(request, 'crm/partials/company_form_modal.html', {'form': form}, status=422)
    else:
        form = CompanyForm()

    return render(request, 'crm/partials/company_form_modal.html', {'form': form})

@login_required
def search_siret_api(request):
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

@login_required
def contact_list(request):
    companies = Company.objects.all().order_by("name")
    contacts = Contact.objects.select_related("company").order_by("-id")

    # Pagination
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
def contact_list_partial(request):
    query = request.GET.get("q", "").strip()
    company_id = request.GET.get("company", "").strip()

    contacts = Contact.objects.select_related("company").all()

    if query:
        contacts = contacts.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(company__name__icontains=query)
        )

    if company_id and company_id.isdigit():
        contacts = contacts.filter(company_id=company_id)

    contacts = contacts.order_by("-id")

    paginator = Paginator(contacts, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "crm/partials/contact_grid.html",
        {
            "contacts": page_obj,
            "page_obj": page_obj,
        },
    )