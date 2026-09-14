"""
Django settings for the Elasticsearch Search Platform.

Configuration is environment-driven. See .env.example at the repository
root for the full list of supported variables. No secrets are stored in
this file.

The platform intentionally enables only the Django components that are
genuinely required. See docs/02-non-goals.md: this is a search platform,
not a content, auth, or session application.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repository root if it exists. Development convenience;
# in production the environment is expected to be populated by the runtime.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(name, "")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or (default or [])


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = _env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
# Only the components that are genuinely required are enabled:
#   contenttypes, auth : required transitively by Django REST Framework.
#   staticfiles        : serves Swagger UI assets added in Phase 1.5.
# `admin`, `sessions`, and `messages` are intentionally omitted
# (docs/02-non-goals.md section 2.5).
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# The platform does not use a relational database as its system of record
# (docs/02-non-goals.md section 3.3). Django still requires a DATABASES
# entry to boot; in-memory SQLite satisfies the framework without writing
# any artifact to disk.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False  # API and documentation are English-only.
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
