from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
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