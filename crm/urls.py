from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    path('clients/', views.company_list, name='company_list'),
    path('clients/<int:page>/', views.company_list_paginated, name='company_list_paginated'),
    path('client/<int:pk>/', views.company_detail, name='company_detail'),
    path('clients/nouvelle-societe/', views.create_company, name='create_company'),
    path("clients/recherche-siret/", views.search_siret_api, name="search_siret_api",),
    path("contacts/", views.contact_list, name="contact_list"),
    path('contacts/<int:page>/', views.contact_list_paginated, name='contact_list_paginated'),
    path('contact/<int:pk>/', views.contact_detail, name='contact_detail'),
    path('contacts/nouveau-contact/', views.create_contact, name='create_contact'),
]