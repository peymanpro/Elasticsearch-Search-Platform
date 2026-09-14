"""
DRF exception handler.

Translates domain exceptions and search-backend failures into the
shaped JSON error described in docs/24-search-api.md section 7. Without
this handler, DRF would return its own ``{"detail": "..."}`` shape,
which does not carry a stable ``code`` field and is therefore harder
for an automated caller to branch on.

The handler is registered in ``settings.REST_FRAMEWORK`` under the
``EXCEPTION_HANDLER`` key. It replaces DRF's default handler; the
default response body is not produced for any exception that reaches
this function.
"""

from __future__ import annotations

from typing import Any

from elastic_transport import ConnectionError as TransportConnectionError
from elastic_transport import TransportError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from apps.search.domain.exceptions import (
    DomainError,
    InvalidPaginationError,
    InvalidSearchQueryError,
)


# Statuses DRF will surface but that are not domain errors. These are
# kept in the response body so that the caller can still see which field
# failed validation; only the wrapping shape changes.
def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """
    Return the shaped error response for an exception, or None.

    Returning None tells DRF to fall through to its own handling, which
    will produce a 500. The platform aims to return shaped errors for
    every failure mode it can classify; a return of None therefore
    means the exception was not anticipated and the traceback is the
    right response for a developer to see.
    """
    # --- Domain validation errors -> 400 ---
    if isinstance(
        exc,
        (
            DomainError,
            InvalidPaginationError,
            InvalidSearchQueryError,
        ),
    ):
        return Response(
            _error_body("invalid_request", str(exc)),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- Elasticsearch transport errors -> 503 or 504 ---
    if isinstance(exc, TransportConnectionError):
        return Response(
            _error_body(
                "backend_unavailable",
                "the search backend is not reachable",
            ),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, TransportError):
        # A transport error with a status code means the server
        # answered with an error. Timeouts are 504; everything else is
        # a backend failure from the caller's point of view.
        code = getattr(exc, "status_code", None)
        if code == 408 or "timeout" in str(exc).lower():
            return Response(
                _error_body("backend_timeout", "the search backend timed out"),
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        return Response(
            _error_body(
                "backend_unavailable",
                f"the search backend returned an error: {exc}",
            ),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # --- Everything else: defer to DRF ---
    # This preserves DRF's behavior for its own ValidationError,
    # NotFound, MethodNotAllowed, etc. The shaped error is applied only
    # to the categories above.
    return drf_default_handler(exc, context)


__all__ = ["api_exception_handler"]
