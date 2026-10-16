from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("toggle-theme/", views.toggle_theme, name="toggle_theme"),
    path("session/ping/", views.session_ping, name="session_ping"),
    path("recherche/", views.global_search, name="global_search"),
]
