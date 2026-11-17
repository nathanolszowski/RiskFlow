"""Local settings: the app runs in Docker on one PC and is only reached from that PC.

Served over plain HTTP on localhost, so there is no HTTPS redirect, HSTS or secure
cookie. Secrets and database come from the environment, with no default: a missing
variable must fail at startup, not at the first query.
"""

import os

from .base import *


def _env_list(name, default):
    values = [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]
    return values or default


DEBUG = False

SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"])
CSRF_TRUSTED_ORIGINS = _env_list(
    "CSRF_TRUSTED_ORIGINS", ["http://localhost:8000", "http://127.0.0.1:8000"]
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# Static files are served by WhiteNoise (gunicorn does not serve them)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))

# Uploads live outside the code, in a folder mounted from the disk
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

# Logs go to the standard output (docker compose logs) and to a rotating file
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "riskflow.log",
            "maxBytes": 5_000_000,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
