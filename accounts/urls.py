from django.urls import path
from . import views

urlpatterns = [
    # L'URL sera exactement /login/
    path('login/', views.login_view, name='login'),
]