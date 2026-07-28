from django.urls import path
from . import views

app_name = 'inspections'

urlpatterns = [
    path("dossiers/", views.folder_list, name="folder_list"),
    path("dossiers/page/<int:page>/", views.folder_list_paginated, name="folder_list_paginated"),
    path("dossiers/edition/", views.create_folder, name="create_folder"),
    path("dossier/<int:pk>/", views.folder_detail, name="folder_detail"),
    # Tabs
    path("dossier/<int:pk>/tabs/overview/", views.folder_tab_overview, name="folder_tab_overview"),
    path("dossier/<int:pk>/tabs/visit/", views.folder_tab_visit, name="folder_tab_visit"),
    path("dossier/<int:pk>/tabs/recommandations/", views.folder_tab_recommandations, name="folder_tab_recommandations"),
]