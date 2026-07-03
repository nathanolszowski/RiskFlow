from django.urls import path
from . import views

urlpatterns = [
    path('dossiers/', views.folders_view, name='folders'),
]