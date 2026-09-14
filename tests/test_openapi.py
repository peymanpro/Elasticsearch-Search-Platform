"""
Tests for the OpenAPI schema and Swagger UI.

The schema is not just a documentation surface: it is a regression guard.
If an API view acquires a serializer that drf-spectacular cannot introspect,
or if a decorator is misused, the schema will fail to generate. These tests
catch that before it reaches a running deployment.
"""

from __future__ import annotations

import yaml
from rest_framework.test import APIClient


def _fetch_schema_payload() -> dict:
    client = APIClient()
    response = client.get("/api/schema/", HTTP_ACCEPT="application/yaml")
    assert response.status_code == 200
    return yaml.safe_load(response.content)


def test_schema_endpoint_returns_yaml() -> None:
    client = APIClient()
    response = client.get("/api/schema/", HTTP_ACCEPT="application/yaml")
    assert response.status_code == 200
    assert "yaml" in response["Content-Type"] or "yml" in response["Content-Type"]


def test_schema_declares_openapi_3() -> None:
    schema = _fetch_schema_payload()
    assert "openapi" in schema
    assert schema["openapi"].startswith("3.")


def test_schema_contains_service_metadata() -> None:
    schema = _fetch_schema_payload()
    info = schema.get("info", {})
    assert info.get("title") == "Elasticsearch Search Platform API"
    assert info.get("version") == "0.1.0"


def test_schema_documents_the_service_root_endpoint() -> None:
    schema = _fetch_schema_payload()
    paths = schema.get("paths", {})
    assert "/" in paths
    assert "get" in paths["/"]


def test_swagger_ui_endpoint_serves_html() -> None:
    client = APIClient()
    response = client.get("/api/docs/")
    assert response.status_code == 200
    body = response.content.decode("utf-8", errors="replace").lower()
    assert "swagger" in body
