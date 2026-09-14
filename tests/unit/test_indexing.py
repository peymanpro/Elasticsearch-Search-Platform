"""Unit tests for the indexing result value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.search.domain.indexing import IndexingFailure, IndexingResult


def test_empty_result_is_fully_successful() -> None:
    r = IndexingResult(succeeded=0, failed=0)
    assert r.is_fully_successful is True
    assert r.total == 0
    assert r.failures == ()


def test_all_succeeded_result() -> None:
    r = IndexingResult(succeeded=100, failed=0)
    assert r.is_fully_successful is True
    assert r.total == 100


def test_partial_failure_result() -> None:
    failures = (
        IndexingFailure(document_id="A", reason="mapping error", status=400),
        IndexingFailure(document_id="B", reason="thread pool full", status=429),
    )
    r = IndexingResult(succeeded=98, failed=2, failures=failures)
    assert r.is_fully_successful is False
    assert r.total == 100
    assert len(r.failures) == 2


def test_all_failed_result() -> None:
    failures = (
        IndexingFailure(document_id="A", reason="mapping error", status=400),
        IndexingFailure(document_id="B", reason="mapping error", status=400),
        IndexingFailure(document_id="C", reason="mapping error", status=400),
    )
    r = IndexingResult(succeeded=0, failed=3, failures=failures)
    assert r.is_fully_successful is False
    assert r.total == 3


def test_indexing_failure_holds_all_fields() -> None:
    f = IndexingFailure(document_id="SKU-1", reason="bad value", status=400)
    assert f.document_id == "SKU-1"
    assert f.reason == "bad value"
    assert f.status == 400


def test_indexing_failure_is_immutable() -> None:
    f = IndexingFailure(document_id="SKU-1", reason="bad value", status=400)
    with pytest.raises(FrozenInstanceError):
        f.reason = "other"  # type: ignore[misc]


def test_indexing_result_is_immutable() -> None:
    r = IndexingResult(succeeded=1, failed=0)
    with pytest.raises(FrozenInstanceError):
        r.succeeded = 2  # type: ignore[misc]


def test_failures_default_to_empty_tuple() -> None:
    r = IndexingResult(succeeded=5, failed=0)
    assert r.failures == ()
