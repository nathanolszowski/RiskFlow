"""Production settings: DEBUG off, secrets and database required from the environment, HTTPS."""

import os

from .base import *


def _env_list(name):
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


DEBUG = False

# No default: the server refuses to start without a real key
SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000

# No defaults: a missing variable must fail at startup, not at the first query
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "require")},
    }
}

# Private S3-compatible storage (Cloudflare R2 speaks the standard S3 protocol).
# Removing AWS_S3_ENDPOINT_URL is enough to switch to AWS S3.
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3.S3Storage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or None
AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "auto")
# Private bucket: URLs are signed and expire after 5 minutes
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 300
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
