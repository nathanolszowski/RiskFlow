"""URLs of the accounts app: login, logout and profile."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="accounts:login"),
        name="logout",
    ),
    path("profil/", views.profile, name="profile"),
    path("profil/email/", views.profile_email, name="profile_email"),
    path("profil/adresse/", views.profile_address, name="profile_address"),
    path("profil/mot-de-passe/", views.profile_password, name="profile_password"),
]
