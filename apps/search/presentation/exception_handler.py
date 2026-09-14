"""
DRF exception handler.

Translates domain exceptions and search-backend failures into the
shaped JSON error described in docs/24-search-api.md section 7.
Without this handler, DRF would return its own ``{"detail": "..."}``
shape, which does not carry a stable ``code`` field and is therefore
harder for an automated caller to branch on.

The handler is registered in ``settings.REST_FRAMEWORK`` under the
``EXCEPTION_HANDLER`` key.

What is handled
---------------
* Domain errors (validation of value objects) -> 400
* Elasticsearch connection failures -> 503
* Elasticsearch connection timeouts -> 504
* Elasticsearch "missing index" errors -> 503 (the alias the
  platform targets does not resolve; the caller cannot do anything
  about that, and the code makes the situation diagnosable)
* DRF's own validation errors -> wrapped in the same shape

Everything else defers to DRF. A failure mode that is not anticipated
produces DRF's default 500, which is the right response: the caller
cannot recover, and the traceback is useful to the developer.
"""

from __future__ import annotations

from typing import Any

from elastic_transport import ConnectionError as TransportConnectionError
from elastic_transport import ConnectionTimeout, TransportError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from apps.search.domain.exceptions import DomainError
from elasticsearch import NotFoundError as ElasticsearchNotFoundError


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Return the shaped error response for an exception, or None."""

    # --- Domain validation errors -> 400 ---
    # DomainError is the base class for every domain exception
    # (InvalidSearchQueryError, InvalidPaginationError,
    # InvalidFiltersError, InvalidSuggestQueryError). Catching the base
    # keeps this branch a single line.
    if isinstance(exc, DomainError):
        return Response(
            _error_body("invalid_request", str(exc)),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- DRF validation errors -> 400, in the shaped body ---
    # DRF would otherwise produce {"field": ["error"]}, which does not
    # carry a code. The handler wraps it while preserving the field
    # details so a caller can still see which field failed.
    if isinstance(exc, DRFValidationError):
        return Response(
            _error_body(
                "invalid_request",
                "one or more request fields failed validation",
                details=exc.detail if hasattr(exc, "detail") else None,
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- Elasticsearch timeouts -> 504 ---
    # Checked before ConnectionError because a timeout is a distinct
    # failure mode for the caller (the backend is slow, not down).
    if isinstance(exc, ConnectionTimeout):
        return Response(
            _error_body("backend_timeout", "the search backend timed out"),
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    # --- Elasticsearch connection failures -> 503 ---
    if isinstance(exc, TransportConnectionError):
        return Response(
            _error_body(
                "backend_unavailable",
                "the search backend is not reachable",
            ),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # --- Elasticsearch "missing index" -> 503 ---
    # A search against an alias that does not resolve produces a
    # NotFoundError whose body describes the missing index. This is
    # not an HTTP 404 for the caller (the path exists); it is a
    # configuration problem the caller cannot fix. 503 with a
    # distinct diagnostic is the correct response.
    if isinstance(exc, ElasticsearchNotFoundError):
        return Response(
            _error_body(
                "backend_unavailable",
                "the search backend reports the target index as missing",
            ),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # --- Other transport errors -> 503 ---
    # Any other TransportError (a 4xx or 5xx returned by the server,
    # a serialization error, etc.) is a backend failure from the
    # caller's point of view.
    if isinstance(exc, TransportError):
        return Response(
            _error_body(
                "backend_unavailable",
                f"the search backend returned an error: {exc}",
            ),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # --- Everything else: defer to DRF ---
    return drf_default_handler(exc, context)


__all__ = ["api_exception_handler"]
