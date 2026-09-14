"""
Bootstrap smoke tests.

These verify that the Django project configures and can serve a request
through the DRF request/response cycle. They are deliberately minimal —
they exist to catch configuration drift, not to test search behavior,
which does not yet exist.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.test import APIClient


def test_settings_load_with_expected_root_urlconf() -> None:
    assert settings.ROOT_URLCONF == "config.urls"


def test_drf_is_registered_in_installed_apps() -> None:
    assert "rest_framework" in settings.INSTALLED_APPS


def test_search_app_is_registered_in_installed_apps() -> None:
    assert "apps.search" in settings.INSTALLED_APPS


def test_service_root_endpoint_returns_identity_via_drf() -> None:
    client = APIClient()
    response = client.get("/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    payload = response.json()
    assert payload["service"] == "elasticsearch-search-platform"
    # The stub probe in Phase 2.2 always reports "unreachable", so the
    # state is "degraded". This will flip to "healthy" in Phase 2.4, when
    # the real Elasticsearch-backed probe replaces the stub.
    assert payload["status"] in {"healthy", "degraded"}


def test_internationalisation_is_disabled() -> None:
    # The API is English-only; multilingualism lives in the search data,
    # not in the framework. See docs/02-non-goals.md section 4.4.
    assert settings.USE_I18N is False
