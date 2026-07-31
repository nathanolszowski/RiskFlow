from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('dashboard/', views.dashboard_test, name='dashboard'),
    path('toggle-theme/', views.toggle_theme, name='toggle_theme'),
    path('recherche/', views.global_search, name='global_search'),
]