from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    path('companies/', views.company_list_view, name='company_list'),
]