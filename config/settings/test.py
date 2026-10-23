"""Test settings: dev settings made fast and isolated (no browser reload, temporary media)."""

import tempfile
from pathlib import Path

from .dev import *

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django_browser_reload"]
MIDDLEWARE = [
    mw
    for mw in MIDDLEWARE
    if mw != "django_browser_reload.middleware.BrowserReloadMiddleware"
]

# Fast hasher: tests create many users
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "riskflow-tests",
    }
}

# Never read from the environment: the INSEE API is always mocked in tests
INSEE_API_KEY = "test"

# Geocoding and routing are always mocked in tests (the Géoplateforme is never called):
# tests of the geo services turn the geocoding on with ``override_settings``
GEOCODING_ENABLED = False
GEOCODING_MIN_SCORE = 0.5
GEOPF_GEOCODING_URL = "https://geocodage.test"
GEOPF_ROUTING_URL = "https://itineraire.test"

# Uploaded files never reach the real media/ folder
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="riskflow-test-media-"))
STORAGES = {
    **STORAGES,
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
}

TEST_RUNNER = "config.test_runner.AppsDiscoverRunner"
