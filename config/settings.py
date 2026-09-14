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
#   rest_framework     : the HTTP layer used by every API endpoint.
# `admin`, `sessions`, and `messages` are intentionally omitted
# (docs/02-non-goals.md section 2.5).
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.search",
    "drf_spectacular",
]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Assigns a correlation ID to the request, stores it in a
    # contextvar, and emits structured start/end log lines. See
    # docs/29-observability.md section 6.
    "apps.search.presentation.middleware.CorrelationIdMiddleware",
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
# entry to boot, and Django's bundled apps (contenttypes, auth) ship
# migrations that must be applied for the framework to be consistent.
#
# The path is configurable so that two scenarios both work:
#
#   * On the host (tests, ad-hoc management commands): :memory: is the
#     default. Nothing persists, which is fine because the tests create
#     and tear down their own isolated database.
#
#   * Inside the web container: DJANGO_SQLITE_PATH points at a writable
#     file path inside the container (see docker-compose.yml). A file is
#     required because the container runs `migrate` and `runserver` as
#     two separate processes; an in-memory database would be created by
#     `migrate`, discarded when that process exits, and then missing when
#     `runserver` starts - which causes Django to print the "unapplied
#     migrations" warning on every boot.
SQLITE_PATH = os.environ.get("DJANGO_SQLITE_PATH", ":memory:")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
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
# Django REST Framework
# ---------------------------------------------------------------------------
# Deliberately minimal. Every additional concern (authentication, throttling,
# pagination, custom exception handling, filtering backends) is added at the
# phase that introduces it, with a recorded rationale.
REST_FRAMEWORK = {
    # drf-spectacular requires DRF to use its AutoSchema. Without this
    # setting, DRF falls back to rest_framework.schemas.openapi.AutoSchema,
    # and drf-spectacular's generator refuses to process any view, raising
    # an AssertionError on schema generation.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": (
        [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ]
        if DEBUG
        else [
            "rest_framework.renderers.JSONRenderer",
        ]
    ),
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    # No authentication classes are configured at this phase. The API is a
    # demonstration surface, not a production service (docs/02-non-goals.md
    # section 2.1).
    "UNAUTHENTICATED_USER": None,
    # The exception handler shapes domain errors and backend failures.
    # See apps/search/presentation/exception_handler.py.
    "EXCEPTION_HANDLER": "apps.search.presentation.exception_handler.api_exception_handler",
}


# ---------------------------------------------------------------------------
# OpenAPI / Swagger (drf-spectacular)
# ---------------------------------------------------------------------------
# The schema is generated from DRF view metadata and drf-spectacular
# annotations. Its purpose is threefold: human-readable API documentation
# (Swagger UI), machine-readable contract for clients, and a regression
# surface — tests assert the schema generates successfully, which catches
# decorator drift as the API grows.
SPECTACULAR_SETTINGS = {
    "TITLE": "Elasticsearch Search Platform API",
    "DESCRIPTION": (
        "A search platform over a medical-products catalog, built on "
        "Elasticsearch and exposed through Django REST Framework.\n\n"
        "The repository demonstrates explicit mappings, custom analyzers, "
        "relevance engineering, fuzzy and phrase matching, synonyms, "
        "autocomplete, filtering, faceted search, highlighting, "
        "explainability, bulk indexing, and zero-downtime reindexing."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        # Injects the current request's correlation ID onto every log
        # record so the formatter can render it. See
        # docs/29-observability.md section 8.
        "correlation_id": {
            "()": "apps.search.presentation.logging_filter.CorrelationIdFilter",
        },
    },
    "formatters": {
        # The correlation ID is a bracketed field at the front so that
        # a log line can be grepped by ID at a glance.
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["correlation_id"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # The platform's own loggers set their level explicitly and let
        # records propagate to the root handler. Attaching handlers to
        # each logger would cause double emission, and setting
        # ``propagate: False`` would prevent pytest's caplog from
        # seeing the records during tests. The root logger's console
        # handler (above) is the single destination.
        "apps.search": {
            "level": "INFO",
            "propagate": True,
        },
        "infrastructure.elasticsearch": {
            "level": "INFO",
            "propagate": True,
        },
    },
}
