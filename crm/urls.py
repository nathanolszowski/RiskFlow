from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    path('companies/', views.company_list_view, name='company_list'),
    path('companies/<int:pk>/', views.company_detail_view, name='company_detail'),
    path('companies/nouvelle-societe/', views.create_company_htmx, name='create_company_htmx'),
    path("companies/recherche-siret/", views.search_siret_api, name="search_siret_api",),
    path("contacts/", views.contact_list, name="contact_list"),
    path('contacts/partial/', views.contact_list_partial, name='contact_list_partial'),
    #path('contacts/<int:pk>/', views.contact_detail, name='contact_detail'),
]