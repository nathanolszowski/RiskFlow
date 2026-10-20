"""URLs of the inspections app: folders, visits, recommendations, templates and the visit form."""

from django.urls import path

from . import views, views_templates, views_visit_form

app_name = "inspections"

urlpatterns = [
    path("dossiers/", views.folder_list, name="folder_list"),
    path(
        "dossiers/page/<int:page>/",
        views.folder_list_paginated,
        name="folder_list_paginated",
    ),
    path("dossiers/edition/", views.create_folder, name="create_folder"),
    path(
        "dossiers/societe/<int:company_id>/",
        views.company_folders_panel,
        name="company_folders_panel",
    ),
    path("dossier/<int:pk>/", views.folder_detail, name="folder_detail"),
    path(
        "dossier/<int:pk>/edition/",
        views.folder_inline_update,
        name="folder_inline_update",
    ),
    path(
        "dossier/<int:pk>/lecture/", views.folder_inline_read, name="folder_inline_read"
    ),
    path(
        "dossier/<int:folder_id>/archive/", views.folder_archive, name="folder_archive"
    ),
    path(
        "dossier/<int:folder_id>/desarchive/",
        views.folder_unarchive,
        name="folder_unarchive",
    ),
    path(
        "dossier/<int:folder_id>/supprimer/", views.folder_delete, name="folder_delete"
    ),
    # Visits
    path(
        "dossier/<int:folder_id>/visite/creer/", views.visit_create, name="visit_create"
    ),
    path("visite/<int:pk>/edition/", views.visit_update, name="visit_update"),
    path(
        "visite/<int:pk>/effectuee/", views.visit_toggle_done, name="visit_toggle_done"
    ),
    path("visite/<int:pk>/archive/", views.visit_archive, name="visit_archive"),
    path("visite/<int:pk>/desarchive/", views.visit_unarchive, name="visit_unarchive"),
    path("visite/<int:pk>/supprimer/", views.visit_delete, name="visit_delete"),
    # Visit form (filling on the field)
    path("visite/<int:pk>/formulaire/", views_visit_form.visit_form, name="visit_form"),
    path(
        "visite/<int:pk>/formulaire/section/<str:section_id>/",
        views_visit_form.visit_form_section,
        name="visit_form_section",
    ),
    path(
        "visite/<int:pk>/reponses/",
        views_visit_form.visit_save_answers,
        name="visit_save_answers",
    ),
    path(
        "visite/<int:pk>/terminer/",
        views_visit_form.visit_complete,
        name="visit_complete",
    ),
    path(
        "visite/<int:pk>/rouvrir/", views_visit_form.visit_reopen, name="visit_reopen"
    ),
    # Visit templates
    path("modeles/", views_templates.template_panel, name="template_panel"),
    path("modeles/creer/", views_templates.template_create, name="template_create"),
    path(
        "modeles/editeur/operation/",
        views_templates.template_editor_operation,
        name="template_editor_operation",
    ),
    path(
        "modeles/<int:pk>/edition/", views_templates.template_edit, name="template_edit"
    ),
    path(
        "modeles/<int:pk>/lecture/", views_templates.template_read, name="template_read"
    ),
    path(
        "modeles/<int:pk>/dupliquer/",
        views_templates.template_duplicate,
        name="template_duplicate",
    ),
    path(
        "modeles/<int:pk>/partage/",
        views_templates.template_toggle_share,
        name="template_toggle_share",
    ),
    path(
        "modeles/<int:pk>/archive/",
        views_templates.template_archive,
        name="template_archive",
    ),
    path(
        "modeles/<int:pk>/desarchive/",
        views_templates.template_unarchive,
        name="template_unarchive",
    ),
    path(
        "modeles/<int:pk>/supprimer/",
        views_templates.template_delete,
        name="template_delete",
    ),
    # Recommandations
    path(
        "recommandation/<int:pk>/edition/",
        views.recommandation_inline_update,
        name="recommandation_inline_update",
    ),
    path(
        "recommandation/<int:pk>/lecture/",
        views.recommandation_inline_read,
        name="recommandation_inline_read",
    ),
    path(
        "recommandation/<int:pk>/archive/",
        views.recommandation_archive,
        name="recommandation_archive",
    ),
    path(
        "recommandation/<int:pk>/desarchive/",
        views.recommandation_unarchive,
        name="recommandation_unarchive",
    ),
    path(
        "recommandation/<int:pk>/supprimer/",
        views.recommandation_delete,
        name="recommandation_delete",
    ),
    # Tabs
    path(
        "dossier/<int:pk>/tabs/overview/",
        views.folder_tab_overview,
        name="folder_tab_overview",
    ),
    path(
        "dossier/<int:pk>/tabs/visit/", views.folder_tab_visit, name="folder_tab_visit"
    ),
    path(
        "dossier/<int:pk>/tabs/recommandations/",
        views.folder_tab_recommandations,
        name="folder_tab_recommandations",
    ),
]
