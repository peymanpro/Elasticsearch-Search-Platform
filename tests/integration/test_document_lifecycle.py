"""
Integration tests for the four document lifecycle operations.

These tests require a running Elasticsearch cluster (docker compose
up). They create a temporary index, exercise each operation, and
delete the index on teardown. The index uses a unique name per run so
that concurrent runs do not interfere.

The tests skip cleanly when the cluster is unreachable, so the rest
of the test suite remains green in environments without Docker.
"""

from __future__ import annotations

import uuid
from contextlib import suppress

import pytest

from elasticsearch import NotFoundError
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import (
    delete_document,
    document_exists,
    get_document,
    index_document,
)
from infrastructure.elasticsearch.health import ping

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture()
def temp_index() -> str:
    """
    Yield the name of a freshly created, empty index, then delete it.
    """
    name = f"esp-lifecycle-test-{uuid.uuid4().hex[:12]}"
    client = get_client()
    client.indices.create(
        index=name,
        settings={"number_of_shards": 1, "number_of_replicas": 0},
    )
    try:
        yield name
    finally:
        with suppress(Exception):
            client.indices.delete(index=name, ignore_unavailable=True)


def test_index_then_get_roundtrip(temp_index: str) -> None:
    source = {"sku": "T-1", "name": "Test Product", "price": 9.99}
    response = index_document(
        index=temp_index,
        document_id="T-1",
        source=source,
        refresh=True,
    )
    assert response["result"] == "created"

    fetched = get_document(index=temp_index, document_id="T-1")
    assert fetched == source


def test_reindexing_the_same_id_replaces_not_duplicates(temp_index: str) -> None:
    source_v1 = {"sku": "T-2", "name": "V1"}
    source_v2 = {"sku": "T-2", "name": "V2", "price": 5.0}

    first = index_document(index=temp_index, document_id="T-2", source=source_v1, refresh=True)
    assert first["result"] == "created"

    second = index_document(index=temp_index, document_id="T-2", source=source_v2, refresh=True)
    assert second["result"] == "updated"

    fetched = get_document(index=temp_index, document_id="T-2")
    assert fetched == source_v2


def test_get_missing_document_returns_none(temp_index: str) -> None:
    assert get_document(index=temp_index, document_id="does-not-exist") is None


def test_exists_reports_presence(temp_index: str) -> None:
    index_document(index=temp_index, document_id="T-3", source={"x": 1}, refresh=True)
    assert document_exists(index=temp_index, document_id="T-3") is True
    assert document_exists(index=temp_index, document_id="other") is False


def test_delete_removes_document(temp_index: str) -> None:
    index_document(index=temp_index, document_id="T-4", source={"x": 1}, refresh=True)
    result = delete_document(index=temp_index, document_id="T-4", refresh=True)
    assert result["result"] == "deleted"
    assert document_exists(index=temp_index, document_id="T-4") is False


def test_delete_missing_document_is_idempotent(temp_index: str) -> None:
    result = delete_document(index=temp_index, document_id="never-existed")
    assert result["result"] == "not_found"


def test_refresh_makes_writes_visible_to_search(temp_index: str) -> None:
    # Index without refresh; then explicitly refresh and search.
    index_document(index=temp_index, document_id="T-5", source={"x": 1})
    client = get_client()
    client.indices.refresh(index=temp_index)
    hits = client.search(index=temp_index, query={"match_all": {}})
    ids = [h["_id"] for h in hits["hits"]["hits"]]
    assert "T-5" in ids


def test_get_on_wrong_index_raises_not_found(temp_index: str) -> None:
    # A non-existent index should not be silently treated as a missing
    # document; the caller must know the index itself is absent.
    fake_index = f"esp-does-not-exist-{uuid.uuid4().hex[:8]}"
    with pytest.raises(NotFoundError):
        client = get_client()
        client.get(index=fake_index, id="anything")
