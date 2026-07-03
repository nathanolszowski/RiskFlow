from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def dashboard_test(request):
    return render(request, 'accounts/dashboard.html')