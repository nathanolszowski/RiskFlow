from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from crm.services.company import INSEEApiClient

from .forms import CompanyForm
from .models import Company
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