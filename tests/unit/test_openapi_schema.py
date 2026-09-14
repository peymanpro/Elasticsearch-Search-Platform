"""
Assertions about the shape of the generated OpenAPI schema.

The schema is a fact about the platform: it declares the request and
response shapes of every public endpoint. A regression in the
declarations (a missing path, a missing component, a dropped example)
is a regression in the API's contract, and it should be caught by a
test rather than discovered by an integrating client.

These tests fetch the schema through the DRF test client and parse it
with ``yaml``. They do not require a running Elasticsearch cluster: the
schema generator introspects view decorators and serializer classes,
not the search backend.
"""

from __future__ import annotations

import yaml
from rest_framework.test import APIClient


def _fetch_schema() -> dict:
    client = APIClient()
    response = client.get("/api/schema/", HTTP_ACCEPT="application/yaml")
    assert response.status_code == 200
    return yaml.safe_load(response.content)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EXPECTED_PATHS = (
    "/",
    "/api/search/",
    "/api/suggest/",
    "/api/explain/",
    "/api/health/",
)


def test_schema_declares_every_public_endpoint() -> None:
    schema = _fetch_schema()
    paths = schema.get("paths", {})
    for expected in EXPECTED_PATHS:
        assert expected in paths, f"missing path: {expected}"


def test_search_endpoint_is_post_only() -> None:
    schema = _fetch_schema()
    search = schema["paths"]["/api/search/"]
    assert "post" in search
    assert "get" not in search


def test_suggest_endpoint_is_get_only() -> None:
    schema = _fetch_schema()
    suggest = schema["paths"]["/api/suggest/"]
    assert "get" in suggest
    assert "post" not in suggest


def test_explain_endpoint_is_post_only() -> None:
    schema = _fetch_schema()
    explain = schema["paths"]["/api/explain/"]
    assert "post" in explain


def test_health_endpoint_is_get_only() -> None:
    schema = _fetch_schema()
    health = schema["paths"]["/api/health/"]
    assert "get" in health


# ---------------------------------------------------------------------------
# Components (error shape)
# ---------------------------------------------------------------------------
def test_api_error_component_is_declared() -> None:
    schema = _fetch_schema()
    components = schema.get("components", {})
    schemas = components.get("schemas", {})
    assert "ApiError" in schemas
    assert "ApiErrorDetail" in schemas


def test_api_error_detail_has_expected_fields() -> None:
    schema = _fetch_schema()
    detail = schema["components"]["schemas"]["ApiErrorDetail"]
    props = detail.get("properties", {})
    assert "code" in props
    assert "message" in props
    assert "details" in props


def test_search_endpoint_documents_error_responses() -> None:
    schema = _fetch_schema()
    search = schema["paths"]["/api/search/"]["post"]
    responses = search.get("responses", {})
    assert "200" in responses
    assert "400" in responses
    assert "503" in responses
    assert "504" in responses


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------
def test_search_endpoint_declares_multiple_examples() -> None:
    schema = _fetch_schema()
    search = schema["paths"]["/api/search/"]["post"]
    request_body = search.get("requestBody", {})
    content = request_body.get("content", {})
    media = content.get("application/json", {})
    examples = media.get("examples", {})
    # The four named examples: simple, filtered, faceted, cursor.
    assert len(examples) >= 4, f"expected at least 4 examples, found {len(examples)}"


def test_search_examples_are_the_curated_ones() -> None:
    schema = _fetch_schema()
    search = schema["paths"]["/api/search/"]["post"]
    examples = search["requestBody"]["content"]["application/json"]["examples"]
    values = list(examples.values())
    # At least one example should reference filters (the "filtered"
    # scenario), one should set include_facets (the "faceted" scenario),
    # and one should set a cursor (the "cursor" scenario).
    filter_examples = [e for e in values if "filters" in e.get("value", {})]
    facet_examples = [e for e in values if e.get("value", {}).get("include_facets") is True]
    cursor_examples = [e for e in values if "cursor" in e.get("value", {})]
    assert filter_examples, "no example declares a filter set"
    assert facet_examples, "no example sets include_facets"
    assert cursor_examples, "no example uses cursor pagination"


def test_explain_endpoint_declares_an_example() -> None:
    schema = _fetch_schema()
    explain = schema["paths"]["/api/explain/"]["post"]
    request_body = explain.get("requestBody", {})
    content = request_body.get("content", {})
    media = content.get("application/json", {})
    examples = media.get("examples", {})
    assert examples, "explain endpoint has no request example"


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------
def test_search_endpoints_are_tagged_search() -> None:
    schema = _fetch_schema()
    for path in ("/api/search/", "/api/suggest/", "/api/explain/"):
        method = "post" if path != "/api/suggest/" else "get"
        tags = schema["paths"][path][method].get("tags", [])
        assert "search" in tags, f"{path} is not tagged search"


def test_health_endpoint_is_tagged_service() -> None:
    schema = _fetch_schema()
    health = schema["paths"]["/api/health/"]["get"]
    assert "service" in health.get("tags", [])
