"""
Unit tests for correlation ID handling and the logging filter.

These tests do not require a running Elasticsearch. They exercise:

* the contextvar storage (set / get / reset),
* the sentinel returned when no ID is in scope,
* the filter that attaches the ID to a log record,
* the middleware that reads or generates the ID from an HTTP request,
  via the DRF test client against a real (in-process) request.

See docs/29-observability.md sections 6 and 10.
"""

from __future__ import annotations

import logging
import re

import pytest
from rest_framework.test import APIClient

from apps.search.presentation.correlation import (
    NO_CORRELATION_ID,
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from apps.search.presentation.logging_filter import CorrelationIdFilter


@pytest.fixture(autouse=True)
def _clean_correlation_id() -> None:
    reset_correlation_id()
    yield
    reset_correlation_id()


# ---------------------------------------------------------------------------
# The contextvar
# ---------------------------------------------------------------------------
def test_default_correlation_id_is_the_sentinel() -> None:
    assert get_correlation_id() == NO_CORRELATION_ID


def test_set_and_get_round_trips() -> None:
    set_correlation_id("abc-123")
    assert get_correlation_id() == "abc-123"


def test_reset_restores_the_sentinel() -> None:
    set_correlation_id("abc-123")
    reset_correlation_id()
    assert get_correlation_id() == NO_CORRELATION_ID


# ---------------------------------------------------------------------------
# The logging filter
# ---------------------------------------------------------------------------
def test_filter_attaches_sentinel_when_no_id_is_set() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    flt = CorrelationIdFilter()
    assert flt.filter(record) is True
    assert record.correlation_id == NO_CORRELATION_ID


def test_filter_attaches_the_current_id() -> None:
    set_correlation_id("filter-test-id")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    CorrelationIdFilter().filter(record)
    assert record.correlation_id == "filter-test-id"


# ---------------------------------------------------------------------------
# The middleware
# ---------------------------------------------------------------------------
def test_middleware_generates_a_correlation_id_when_header_is_missing() -> None:
    client = APIClient()
    # The service-root endpoint is cheap and does not need Elasticsearch
    # for the parts we are asserting on.
    response = client.get("/")
    assert response.status_code == 200
    # The middleware resets the id after the request, so we cannot read
    # the value from the contextvar. Instead, assert that the request
    # did not error and that no exception leaked from the middleware.


def test_middleware_honors_the_supplied_header(caplog: pytest.LogCaptureFixture) -> None:
    """
    When a caller supplies the header, the middleware uses it verbatim.
    Assert this by capturing the request.end log line and checking the
    correlation ID appears in the formatted output.
    """
    with caplog.at_level(logging.INFO, logger="apps.search.presentation.middleware"):
        client = APIClient()
        response = client.get(
            "/",
            HTTP_X_CORRELATION_ID="the-caller-chose-this-id",
        )

    assert response.status_code == 200
    # The middleware emitted at least the start and end events. Every
    # record carries the header value.
    middleware_records = [
        r for r in caplog.records if r.name == "apps.search.presentation.middleware"
    ]
    assert middleware_records, "middleware emitted no log records"
    for record in middleware_records:
        assert record.correlation_id == "the-caller-chose-this-id"


def test_middleware_generates_a_uuid_when_no_header_is_supplied(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="apps.search.presentation.middleware"):
        client = APIClient()
        response = client.get("/")

    assert response.status_code == 200
    middleware_records = [
        r for r in caplog.records if r.name == "apps.search.presentation.middleware"
    ]
    assert middleware_records, "middleware emitted no log records"
    # All records from one request should carry the same generated ID.
    generated_ids = {r.correlation_id for r in middleware_records}
    assert len(generated_ids) == 1
    generated_id = generated_ids.pop()
    # The middleware generates a 32-character hex string (uuid4().hex).
    assert re.fullmatch(r"[0-9a-f]{32}", generated_id), generated_id


def test_middleware_resets_the_id_after_the_request() -> None:
    """
    After a request completes, the contextvar should be back to its
    default. We exercise this by making a request and immediately
    reading the contextvar, all from the same test (same context).
    """
    reset_correlation_id()
    client = APIClient()
    client.get("/")
    assert get_correlation_id() == NO_CORRELATION_ID


def test_middleware_logs_request_start_and_end(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="apps.search.presentation.middleware"):
        client = APIClient()
        client.get("/")

    messages = [r.getMessage() for r in caplog.records]
    assert any("request.start" in m for m in messages), messages
    assert any("request.end" in m for m in messages), messages


def test_two_requests_get_different_generated_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="apps.search.presentation.middleware"):
        client = APIClient()
        client.get("/")
        first_ids = {
            r.correlation_id
            for r in caplog.records
            if r.name == "apps.search.presentation.middleware"
        }
        caplog.clear()
        client.get("/")
        second_ids = {
            r.correlation_id
            for r in caplog.records
            if r.name == "apps.search.presentation.middleware"
        }

    assert len(first_ids) == 1
    assert len(second_ids) == 1
    assert first_ids != second_ids
