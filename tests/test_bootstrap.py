"""
Bootstrap smoke tests.

These verify that the Django project configures and can serve a request.
They are deliberately minimal — they exist to catch configuration drift,
not to test search behavior, which does not yet exist.
"""

from __future__ import annotations

from django.conf import settings
from django.test import Client


def test_settings_load_with_expected_root_urlconf() -> None:
    assert settings.ROOT_URLCONF == "config.urls"


def test_service_root_endpoint_returns_identity() -> None:
    client = Client()
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "elasticsearch-search-platform"
    assert payload["status"] == "ok"


def test_internationalisation_is_disabled() -> None:
    # The API is English-only; multilingualism lives in the search data,
    # not in the framework. See docs/02-non-goals.md section 4.4.
    assert settings.USE_I18N is False
