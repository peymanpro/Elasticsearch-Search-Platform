"""
Correlation ID middleware.

Reads the ``X-Correlation-ID`` header from the incoming request, or
generates a UUID4 if the header is absent. Stores the value in a
contextvar so that every log line emitted while the request is being
served carries it. Resets the contextvar when the request is done.

The middleware also emits two structured log lines, one at the start
and one at the end of the request, with a summary of the request and
its duration. See docs/29-observability.md sections 3 and 6.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.search.presentation.correlation import (
    CORRELATION_ID_HEADER,
    reset_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware:
    """
    Assign, propagate, and log a correlation ID for every request.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # 1) Determine the correlation ID. The header value, when
        # present and non-empty, wins. Otherwise generate one.
        header_value = request.headers.get(CORRELATION_ID_HEADER, "").strip()
        correlation_id = header_value or uuid.uuid4().hex
        set_correlation_id(correlation_id)

        started = time.perf_counter()
        logger.info(
            "request.start method=%s path=%s",
            request.method,
            request.path,
        )

        try:
            response = self._get_response(request)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            # The response is not yet fully known if get_response raised.
            # Logging the end event in a finally ensures we always emit
            # a matching pair, even on unhandled exceptions.
            status = getattr(locals().get("response", None), "status_code", 500)
            logger.info(
                "request.end method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                request.path,
                status,
                duration_ms,
            )
            reset_correlation_id()

        return response


__all__ = ["CorrelationIdMiddleware"]
