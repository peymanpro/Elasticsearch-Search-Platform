"""
Integration tests for the search HTTP API.

These tests use the DRF test client to exercise every endpoint against
a real Elasticsearch cluster. The fixtures ensure that the ``products``
alias exists and points at a test index loaded with the real dataset,
so the endpoints run against realistic data.

The setup saves and restores the original alias target so that tests
are idempotent and do not disturb any real index a user may have set
up.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress

import pytest
from rest_framework.test import APIClient

from apps.search.domain.product_document import ProductDocument
from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer
from infrastructure.datasets.jsonl_reader import read_products
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import (
    INDEX_ALIAS,
    load_mapping,
    load_settings,
)

pytestmark = pytest.mark.integration

TEST_INDEX = "products-apitest"
REPO_ROOT_DATASET = "data/products.jsonl"


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module", autouse=True)
def _api_index(_require_running_elasticsearch: None) -> Iterator[None]:
    """
    Set up a test index, load the real dataset into it, and point the
    products alias at it. Restore the original alias state on teardown.
    """
    client = get_client()

    # 1) Record the current alias target, if any.
    original_target: str | None = None
    try:
        existing = client.indices.get_alias(name=INDEX_ALIAS)
        original_target = next(iter(existing))
    except Exception:  # noqa: BLE001 - alias does not exist yet
        original_target = None

    # 2) Create the test index and load documents.
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)
    settings = load_settings("v2")
    mapping = load_mapping("v2")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={
            "dynamic": mapping["dynamic"],
            "properties": mapping["properties"],
        },
    )

    read_result = read_products(REPO_ROOT_DATASET)
    assert read_result.is_valid, f"dataset invalid: {read_result.errors}"
    documents: list[ProductDocument] = list(read_result.documents)

    indexer = ElasticsearchBulkIndexer(client=client, index=TEST_INDEX, batch_size=10)
    indexing = indexer.index_products(documents)
    assert indexing.failed == 0, f"indexing failed: {indexing.failures}"

    # 3) Move the alias to the test index.
    actions: list[dict] = []
    if original_target is not None:
        actions.append({"remove": {"index": original_target, "alias": INDEX_ALIAS}})
    actions.append({"add": {"index": TEST_INDEX, "alias": INDEX_ALIAS}})
    client.indices.update_aliases(actions=actions)
    client.indices.refresh(index=TEST_INDEX)

    try:
        yield
    finally:
        # Restore the alias and remove the test index. Every step here
        # is best-effort: the test is already done and its result stands
        # regardless of whether cleanup succeeds.
        restore_actions: list[dict] = [{"remove": {"index": TEST_INDEX, "alias": INDEX_ALIAS}}]
        if original_target is not None:
            restore_actions.append({"add": {"index": original_target, "alias": INDEX_ALIAS}})
        with suppress(Exception):
            client.indices.update_aliases(actions=restore_actions)
        with suppress(Exception):
            client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


@pytest.fixture()
def client() -> APIClient:
    return APIClient()


# ---------------------------------------------------------------------------
# POST /api/search/
# ---------------------------------------------------------------------------
def test_search_returns_hits_and_metadata(client: APIClient) -> None:
    response = client.post("/api/search/", {"query": "wireless"}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "wireless"
    assert body["total"] >= 0
    assert "hits" in body
    assert isinstance(body["hits"], list)
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["returned"] == len(body["hits"])


def test_search_with_filter(client: APIClient) -> None:
    response = client.post(
        "/api/search/",
        {"query": "wireless", "filters": {"category": "Electronics"}},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    for hit in body["hits"]:
        assert hit["source"]["category"] == "Electronics"


def test_search_with_sort(client: APIClient) -> None:
    response = client.post(
        "/api/search/",
        {"query": "wireless", "sort": {"field": "price", "direction": "asc"}},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    prices = [hit["source"]["price"] for hit in body["hits"]]
    assert prices == sorted(prices)


def test_search_with_facets(client: APIClient) -> None:
    response = client.post(
        "/api/search/",
        {"query": "wireless", "include_facets": True},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert "facets" in body
    assert body["facets"] is not None
    for facet_key in ("categories", "brands", "availability", "price_ranges"):
        assert facet_key in body["facets"]
        assert isinstance(body["facets"][facet_key], list)


def test_search_without_facets_has_null_facets(client: APIClient) -> None:
    response = client.post("/api/search/", {"query": "wireless"}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body.get("facets") is None


def test_search_with_cursor_pagination(client: APIClient) -> None:
    # "electronics" matches the category field of several fixture
    # documents. With page_size 2 that produces at least two pages,
    # which is what the cursor path needs to exercise.
    query_body = {"query": "electronics", "page_size": 2}

    first = client.post("/api/search/", query_body, format="json").json()
    assert first["page"] == 1
    assert first["total"] >= 2
    assert first["returned"] == 2
    assert first["has_more"] is True

    cursor = first.get("next_cursor")
    assert cursor is not None, "expected a next_cursor on a full page"

    second = client.post(
        "/api/search/",
        {**query_body, "cursor": cursor},
        format="json",
    ).json()
    assert second["page"] is None
    first_ids = {h["id"] for h in first["hits"]}
    second_ids = {h["id"] for h in second["hits"]}
    assert first_ids.isdisjoint(second_ids)


def test_search_missing_query_rejected(client: APIClient) -> None:
    response = client.post("/api/search/", {}, format="json")
    assert response.status_code == 400


def test_search_empty_query_rejected(client: APIClient) -> None:
    response = client.post("/api/search/", {"query": ""}, format="json")
    assert response.status_code == 400


def test_search_page_zero_rejected(client: APIClient) -> None:
    # DRF min_value=1 rejects it before the domain sees it.
    response = client.post(
        "/api/search/",
        {"query": "wireless", "page": 0},
        format="json",
    )
    assert response.status_code == 400


def test_search_cursor_and_page_together_rejected(client: APIClient) -> None:
    response = client.post(
        "/api/search/",
        {"query": "wireless", "page": 2, "cursor": [1.0, "SKU-1"]},
        format="json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/suggest/
# ---------------------------------------------------------------------------
def test_suggest_returns_list(client: APIClient) -> None:
    response = client.get("/api/suggest/?q=wire")
    assert response.status_code == 200
    body = response.json()
    assert body["prefix"] == "wire"
    assert isinstance(body["suggestions"], list)


def test_suggest_missing_q_rejected(client: APIClient) -> None:
    response = client.get("/api/suggest/")
    assert response.status_code == 400


def test_suggest_empty_q_rejected(client: APIClient) -> None:
    response = client.get("/api/suggest/?q=")
    assert response.status_code == 400


def test_suggest_with_limit(client: APIClient) -> None:
    response = client.get("/api/suggest/?q=wire&limit=1")
    assert response.status_code == 200
    body = response.json()
    assert len(body["suggestions"]) <= 1


# ---------------------------------------------------------------------------
# POST /api/explain/
# ---------------------------------------------------------------------------
def test_explain_matching_document(client: APIClient) -> None:
    # Find a real document id from the search endpoint.
    search = client.post("/api/search/", {"query": "wireless"}, format="json").json()
    if not search["hits"]:
        pytest.skip("no matching documents to explain")
    doc_id = search["hits"][0]["id"]

    response = client.post(
        "/api/explain/",
        {"query": "wireless", "document_id": doc_id},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["matched"] is True
    assert body["explanation"] is not None
    assert "value" in body["explanation"]


def test_explain_missing_fields_rejected(client: APIClient) -> None:
    response = client.post("/api/explain/", {"query": "wireless"}, format="json")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/health/
# ---------------------------------------------------------------------------
def test_health_returns_status(client: APIClient) -> None:
    response = client.get("/api/health/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"healthy", "degraded", "unhealthy"}
    assert body["cluster"]["status"] in {"green", "yellow", "red", "unreachable"}
    assert body["index"]["alias"] == INDEX_ALIAS


def test_health_reports_documents_when_available(client: APIClient) -> None:
    response = client.get("/api/health/")
    body = response.json()
    # The test fixture loaded documents into the index the alias points
    # at, so the count should be positive and the status should be
    # healthy.
    assert body["index"]["document_count"] > 0
    assert body["status"] == "healthy"


# ---------------------------------------------------------------------------
# Service root
# ---------------------------------------------------------------------------
def test_service_root_still_works(client: APIClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "elasticsearch-search-platform"
    assert body["status"] in {"healthy", "degraded"}
