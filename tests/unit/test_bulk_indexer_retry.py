"""
Unit tests for the bulk indexer's retry logic.

These tests exercise the retry policy described in
docs/22-indexing.md section 6 and docs/28-operational-resilience.md
section 4. They use a fake client that returns a configurable
sequence of exceptions and successful responses, so the retry path
is exercised without any network.

The backoff delays in the bulk indexer are real (0.5s, 1.0s), which
would make the retry-exhaustion test slow. The tests patch
``time.sleep`` in the bulk indexer module to remove the delay while
preserving the number of retries.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from elastic_transport import ConnectionError as TransportConnectionError
from elastic_transport import ConnectionTimeout

from apps.search.infrastructure.bulk_indexer import ElasticsearchBulkIndexer
from elasticsearch import TransportError


class _ScriptedClient:
    """
    Test double that returns a scripted sequence of responses.

    Each scripted item is either an Exception (to be raised) or a dict
    (to be returned as a successful response). Once the script is
    exhausted, further calls raise an AssertionError so a test that
    retries more than expected fails loudly.
    """

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls: int = 0

    def bulk(self, *, index: str | None = None, operations: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        if not self._script:
            raise AssertionError(f"fake client called more times than scripted (call {self.calls})")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _success_response(items: int = 1) -> dict[str, Any]:
    """A minimal successful Bulk API response for N items."""
    return {
        "took": 1,
        "errors": False,
        "items": [
            {
                "index": {
                    "_index": "test",
                    "_id": f"SKU-{i:04d}",
                    "status": 201,
                    "result": "created",
                }
            }
            for i in range(items)
        ],
    }


def _doc(i: int) -> dict[str, Any]:
    return {"id": f"SKU-{i:04d}", "sku": f"SKU-{i:04d}", "name": f"Product {i}"}


def _indexer(client: _ScriptedClient) -> ElasticsearchBulkIndexer:
    # Batch size larger than the test's document count so a single
    # call to the fake client is made per attempt.
    return ElasticsearchBulkIndexer(client=client, index="test", batch_size=100)


# ---------------------------------------------------------------------------
# Success on first attempt
# ---------------------------------------------------------------------------
def test_successful_first_attempt_does_not_retry() -> None:
    client = _ScriptedClient([_success_response(items=2)])
    indexer = _indexer(client)

    with patch("apps.search.infrastructure.bulk_indexer.time.sleep"):
        result = indexer.index_documents([_doc(0), _doc(1)])

    assert result.succeeded == 2
    assert result.failed == 0
    assert client.calls == 1


# ---------------------------------------------------------------------------
# Transient failure, retry succeeds
# ---------------------------------------------------------------------------
def test_transient_connection_error_is_retried() -> None:
    client = _ScriptedClient(
        [
            TransportConnectionError("refused"),
            _success_response(items=1),
        ]
    )
    indexer = _indexer(client)

    with patch("apps.search.infrastructure.bulk_indexer.time.sleep") as fake_sleep:
        result = indexer.index_documents([_doc(0)])

    assert result.succeeded == 1
    assert result.failed == 0
    assert client.calls == 2
    # The retry should have waited once.
    assert fake_sleep.call_count == 1
    # And the first backoff is the configured initial value.
    first_delay = fake_sleep.call_args_list[0].args[0]
    assert first_delay == pytest.approx(0.5)


def test_transient_timeout_is_retried() -> None:
    # A ConnectionTimeout is a subclass of ConnectionError, so it is
    # treated as transient by the same branch.
    client = _ScriptedClient(
        [
            ConnectionTimeout("timeout"),
            _success_response(items=1),
        ]
    )
    indexer = _indexer(client)

    with patch("apps.search.infrastructure.bulk_indexer.time.sleep"):
        result = indexer.index_documents([_doc(0)])

    assert result.succeeded == 1
    assert client.calls == 2


def test_two_transient_failures_then_success() -> None:
    client = _ScriptedClient(
        [
            TransportConnectionError("refused once"),
            TransportConnectionError("refused twice"),
            _success_response(items=1),
        ]
    )
    indexer = _indexer(client)

    with patch("apps.search.infrastructure.bulk_indexer.time.sleep") as fake_sleep:
        result = indexer.index_documents([_doc(0)])

    assert result.succeeded == 1
    assert client.calls == 3
    # Two retries: 0.5s then 1.0s.
    delays = [call.args[0] for call in fake_sleep.call_args_list]
    assert delays == [pytest.approx(0.5), pytest.approx(1.0)]


# ---------------------------------------------------------------------------
# Retries exhausted
# ---------------------------------------------------------------------------
def test_retries_exhausted_raises_the_final_exception() -> None:
    # MAX_ATTEMPTS is 3 (initial + 2 retries). A script of three
    # failures means the third failure is the one that propagates.
    third = TransportConnectionError("third failure")
    client = _ScriptedClient(
        [
            TransportConnectionError("first failure"),
            TransportConnectionError("second failure"),
            third,
        ]
    )
    indexer = _indexer(client)

    with (
        patch("apps.search.infrastructure.bulk_indexer.time.sleep"),
        pytest.raises(TransportConnectionError) as exc_info,
    ):
        indexer.index_documents([_doc(0)])

    assert exc_info.value is third
    assert client.calls == 3


# ---------------------------------------------------------------------------
# Non-transient errors are not retried
# ---------------------------------------------------------------------------
def test_non_transient_transport_error_is_not_retried() -> None:
    # A TransportError with status_code 400 (Bad Request) is a
    # malformed request, not a transient condition.
    bad_request = TransportError("bad request")
    bad_request.status_code = 400  # type: ignore[attr-defined]
    client = _ScriptedClient([bad_request])
    indexer = _indexer(client)

    with (
        patch("apps.search.infrastructure.bulk_indexer.time.sleep") as fake_sleep,
        pytest.raises(TransportError),
    ):
        indexer.index_documents([_doc(0)])

    assert client.calls == 1
    assert fake_sleep.call_count == 0


# ---------------------------------------------------------------------------
# Retry applies per batch, not per document
# ---------------------------------------------------------------------------
def test_retry_applies_to_each_batch_independently() -> None:
    # Two batches: batch 1 fails once then succeeds; batch 2 succeeds
    # first try. Total fake-client calls: 3.
    client = _ScriptedClient(
        [
            TransportConnectionError("batch 1 first try"),
            _success_response(items=1),
            _success_response(items=1),
        ]
    )
    # Batch size 1 means one document per bulk request.
    indexer = ElasticsearchBulkIndexer(client=client, index="test", batch_size=1)

    with patch("apps.search.infrastructure.bulk_indexer.time.sleep"):
        result = indexer.index_documents([_doc(0), _doc(1)])

    assert result.succeeded == 2
    assert client.calls == 3
