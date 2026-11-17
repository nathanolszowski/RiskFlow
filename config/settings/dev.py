"""Development settings: DEBUG on, local database defaults and browser reload."""

import os

from .base import *

DEBUG = True

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-lirbm$r_%85vin3@k-tud$g%2z_6$lv#xk=q4^rwdpydoz@rqu",
)

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS += ["django_browser_reload"]
MIDDLEWARE += ["django_browser_reload.middleware.BrowserReloadMiddleware"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "riskflow"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}
