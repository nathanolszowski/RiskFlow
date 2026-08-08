from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    # Clients
    path('clients/', views.company_list, name='company_list'),
    path('clients/page/<int:page>/', views.company_list_paginated, name='company_list_paginated'),
    path('client/<int:pk>/', views.company_detail, name='company_detail'),
    path('client/<int:pk>/edition/', views.company_inline_update, name='company_inline_update'),
    path("client/<int:pk>/lecture/", views.company_inline_read, name="company_inline_read",),
    path('clients/nouvelle-societe/', views.create_company, name='create_company'),
    path("client/<int:pk>/archive/", views.company_archive, name="company_archive"),
    path("client/<int:pk>/desarchive/", views.company_unarchive, name="company_unarchive"),
    path("clients/recherche-siret/", views.search_siret_api, name="search_siret_api",),
    # Contacts
    path("contacts/", views.contact_list, name="contact_list"),
    path('contacts/page/<int:page>/', views.contact_list_paginated, name='contact_list_paginated'),
    path('contact/<int:pk>/', views.contact_detail, name='contact_detail'),
    path('contacts/nouveau-contact/', views.create_contact, name='create_contact'),
]