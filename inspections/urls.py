from django.urls import path
from . import views

app_name = 'inspections'

urlpatterns = [
    path('dossiers/', views.folders_view, name='folders'),
    path('nouveau-dossier/', views.create_folder_htmx, name='create_folder_htmx'),
    path('dossier/<int:folder_id>/', views.folder_detail_view, name='folder_detail'),
    path('dossier/<int:folder_id>/tab-overview/', views.folder_tab_overview, name='folder_tab_overview'),
    path('dossier/<int:folder_id>/tab-visit/', views.folder_tab_visit, name='folder_tab_visit'),
    path('dossier/<int:folder_id>/tab-recommandations/', views.folder_tab_recommandations, name='folder_tab_recommandations'),
]