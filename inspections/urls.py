from django.urls import path
from . import views

urlpatterns = [
    path('dossiers/', views.folders_view, name='folders'),
    path('nouveau-dossier/', views.create_folder_htmx, name='create_folder_htmx'),
]