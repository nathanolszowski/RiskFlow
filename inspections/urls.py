from django.urls import path
from . import views

app_name = 'inspections'

urlpatterns = [
    path("dossiers/", views.folder_list, name="folder_list"),
    path("dossiers/page/<int:page>/", views.folder_list_paginated, name="folder_list_paginated"),
    path("dossiers/edition/", views.create_folder, name="create_folder"),
    path("dossier/<int:pk>/", views.folder_detail, name="folder_detail"),
    path("dossier/<int:pk>/edition/", views.folder_inline_update, name="folder_inline_update"),
    path("dossier/<int:pk>/lecture/", views.folder_inline_read, name="folder_inline_read"),
    path("dossier/<int:folder_id>/archive/", views.folder_archive, name="folder_archive"),
    path("dossier/<int:folder_id>/desarchive/", views.folder_unarchive, name="folder_unarchive"),
    path("dossier/<int:folder_id>/supprimer/", views.folder_delete, name="folder_delete"),
    # Visits
    path("visite/<int:pk>/edition/", views.visit_inline_update, name="visit_inline_update"),
    path("visite/<int:pk>/lecture/", views.visit_inline_read, name="visit_inline_read"),
    path("visite/<int:pk>/archive/", views.visit_archive, name="visit_archive"),
    path("visite/<int:pk>/desarchive/", views.visit_unarchive, name="visit_unarchive"),
    path("visite/<int:pk>/supprimer/", views.visit_delete, name="visit_delete"),
    # Recommandations
    path("recommandation/<int:pk>/edition/", views.recommandation_inline_update, name="recommandation_inline_update"),
    path("recommandation/<int:pk>/lecture/", views.recommandation_inline_read, name="recommandation_inline_read"),
    path("recommandation/<int:pk>/archive/", views.recommandation_archive, name="recommandation_archive"),
    path("recommandation/<int:pk>/desarchive/", views.recommandation_unarchive, name="recommandation_unarchive"),
    path("recommandation/<int:pk>/supprimer/", views.recommandation_delete, name="recommandation_delete"),
    # Tabs
    path("dossier/<int:pk>/tabs/overview/", views.folder_tab_overview, name="folder_tab_overview"),
    path("dossier/<int:pk>/tabs/visit/", views.folder_tab_visit, name="folder_tab_visit"),
    path("dossier/<int:pk>/tabs/recommandations/", views.folder_tab_recommandations, name="folder_tab_recommandations"),
]