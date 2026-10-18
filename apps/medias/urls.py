"""URLs of the medias app: folder tab, upload, edition, protected file access and archiving."""

from django.urls import path

from . import views

app_name = "medias"

urlpatterns = [
    path(
        "dossier/<int:pk>/tabs/medias/",
        views.folder_tab_medias,
        name="folder_tab_medias",
    ),
    path(
        "dossier/<int:folder_id>/medias/ajouter/",
        views.media_upload,
        name="media_upload",
    ),
    path("media/<int:pk>/modifier/", views.media_update, name="media_update"),
    path("media/<int:pk>/fichier/", views.media_file, name="media_file"),
    path("media/<int:pk>/miniature/", views.media_thumbnail, name="media_thumbnail"),
    path("media/<int:pk>/archive/", views.media_archive, name="media_archive"),
    path("media/<int:pk>/desarchive/", views.media_unarchive, name="media_unarchive"),
    path("media/<int:pk>/supprimer/", views.media_delete, name="media_delete"),
]
