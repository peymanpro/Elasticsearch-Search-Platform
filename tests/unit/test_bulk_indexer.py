"""
Unit tests for the bulk indexer.

These tests use a fake Elasticsearch client that records the calls
made to ``bulk`` and returns canned responses. No cluster is required.

Integration coverage (indexing real documents into a real index) is
in tests/integration/test_bulk_indexing.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.search.domain.indexing import IndexingResult
from apps.search.infrastructure.bulk_indexer import (
    DEFAULT_BATCH_SIZE,
    ElasticsearchBulkIndexer,
)


class _FakeBulkClient:
    """
    Test double for the Elasticsearch client's bulk method.

    Records every call it receives and returns responses from a
    pre-supplied queue, or a synthetic "all succeeded" response when
    the queue is empty.
    """

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses or [])
        self._empty_response_used = 0

    def bulk(
        self,
        *,
        index: str | None = None,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append({"index": index, "operations": list(operations)})
        if self._responses:
            return self._responses.pop(0)
        # Synthesize a "everything succeeded" response from the ops.
        self._empty_response_used += 1
        return _synthesize_success_response(operations)


def _synthesize_success_response(operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a Bulk API response for the given operations, all successful."""
    items: list[dict[str, Any]] = []
    i = 0
    while i < len(operations):
        action = operations[i]
        if "index" in action:
            meta = action["index"]
            source = operations[i + 1]
            items.append(
                {
                    "index": {
                        "_index": meta.get("_index"),
                        "_id": meta.get("_id"),
                        "status": 201,
                        "result": "created",
                    }
                }
            )
            assert source  # consumed
            i += 2
        elif "delete" in action:
            meta = action["delete"]
            items.append(
                {
                    "delete": {
                        "_index": meta.get("_index"),
                        "_id": meta.get("_id"),
                        "status": 200,
                        "result": "deleted",
                    }
                }
            )
            i += 1
        else:
            raise AssertionError(f"unexpected action: {action}")
    return {"took": 1, "errors": False, "items": items}


def _doc(i: int) -> dict[str, Any]:
    return {
        "id": f"SKU-{i:04d}",
        "sku": f"SKU-{i:04d}",
        "name": f"Product {i}",
        "price": float(i),
    }


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------
def test_indexing_below_batch_size_makes_one_request() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    result = indexer.index_documents([_doc(i) for i in range(3)])

    assert len(client.calls) == 1
    assert result.succeeded == 3
    assert result.failed == 0


def test_indexing_above_batch_size_makes_multiple_requests() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=3)
    result = indexer.index_documents([_doc(i) for i in range(7)])

    # 7 documents at 3 per batch = 3 requests (3, 3, 1).
    assert len(client.calls) == 3
    assert result.succeeded == 7


def test_indexing_exactly_a_multiple_of_batch_size() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=5)
    result = indexer.index_documents([_doc(i) for i in range(10)])

    assert len(client.calls) == 2
    assert result.succeeded == 10


def test_empty_input_makes_no_request() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test")
    result = indexer.index_documents([])

    assert len(client.calls) == 0
    assert result.succeeded == 0
    assert result.failed == 0


# ---------------------------------------------------------------------------
# Idempotency via SKU-based _id
# ---------------------------------------------------------------------------
def test_indexing_uses_the_document_id_as_the_bulk_id() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    indexer.index_documents([_doc(1)])

    call = client.calls[0]
    assert call["index"] == "test"
    operations = call["operations"]
    assert operations[0] == {"index": {"_id": "SKU-0001"}}
    assert operations[1]["id"] == "SKU-0001"


def test_document_without_id_raises() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    with pytest.raises(ValueError, match="missing an 'id' field"):
        indexer.index_documents([{"sku": "X", "name": "no id"}])


# ---------------------------------------------------------------------------
# Partial failures
# ---------------------------------------------------------------------------
def test_partial_failure_is_reported() -> None:
    client = _FakeBulkClient(
        responses=[
            {
                "took": 5,
                "errors": True,
                "items": [
                    {
                        "index": {
                            "_index": "test",
                            "_id": "SKU-0001",
                            "status": 201,
                            "result": "created",
                        }
                    },
                    {
                        "index": {
                            "_index": "test",
                            "_id": "SKU-0002",
                            "status": 400,
                            "error": {
                                "type": "mapper_parsing_exception",
                                "reason": "failed to parse field [price]",
                            },
                        }
                    },
                ],
            }
        ]
    )
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    result = indexer.index_documents([_doc(1), _doc(2)])

    assert result.succeeded == 1
    assert result.failed == 1
    assert result.total == 2
    failure = result.failures[0]
    assert failure.document_id == "SKU-0002"
    assert failure.status == 400
    assert "failed to parse" in failure.reason


def test_all_failures_are_reported() -> None:
    client = _FakeBulkClient(
        responses=[
            {
                "took": 5,
                "errors": True,
                "items": [
                    {
                        "index": {
                            "_index": "test",
                            "_id": f"SKU-{i:04d}",
                            "status": 400,
                            "error": {"type": "x", "reason": f"reason {i}"},
                        }
                    }
                    for i in range(3)
                ],
            }
        ]
    )
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    result = indexer.index_documents([_doc(i) for i in range(3)])

    assert result.succeeded == 0
    assert result.failed == 3
    assert len(result.failures) == 3


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------
def test_delete_uses_the_document_id() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    result = indexer.delete_documents(["SKU-0001", "SKU-0002"])

    assert result.succeeded == 2
    call = client.calls[0]
    assert call["index"] == "test"
    operations = call["operations"]
    assert operations[0]["delete"] == {"_id": "SKU-0001"}
    assert operations[1]["delete"] == {"_id": "SKU-0002"}


def test_delete_of_missing_document_is_a_success() -> None:
    # Elasticsearch returns status 404 with result not_found when the
    # document is absent. That is the desired end state, not a failure.
    client = _FakeBulkClient(
        responses=[
            {
                "took": 5,
                "errors": False,
                "items": [
                    {
                        "delete": {
                            "_index": "test",
                            "_id": "SKU-9999",
                            "status": 404,
                            "result": "not_found",
                        }
                    }
                ],
            }
        ]
    )
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=10)
    result = indexer.delete_documents(["SKU-9999"])

    assert result.succeeded == 1
    assert result.failed == 0


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------
def test_batch_size_must_be_positive() -> None:
    client = _FakeBulkClient()
    with pytest.raises(ValueError, match="batch_size must be >= 1"):
        ElasticsearchBulkIndexer(client=client, index="test", batch_size=0)


def test_default_batch_size_is_documented_value() -> None:
    assert DEFAULT_BATCH_SIZE == 500


# ---------------------------------------------------------------------------
# The return type
# ---------------------------------------------------------------------------
def test_result_is_an_indexing_result() -> None:
    client = _FakeBulkClient()
    indexer = ElasticsearchBulkIndexer(client=client, index="test")
    result = indexer.index_documents([_doc(1)])
    assert isinstance(result, IndexingResult)
