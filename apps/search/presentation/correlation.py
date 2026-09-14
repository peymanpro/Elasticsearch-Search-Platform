"""
Correlation ID storage for the current request.

The correlation ID is a string that identifies one HTTP request. It is
stored in a ``contextvars.ContextVar`` so that every component running
while a request is being served sees the same value, without any need
to pass the ID through function arguments.

``contextvars`` is the right tool for this because:

* The value is per-context (per-request under ASGI / WSGI, per-task
  under asyncio). Concurrent requests do not see each other's IDs.
* No lock is required; the stdlib handles the isolation.
* The mechanism works across the sync/async boundary that Django's
  middleware chain uses.

Outside a request context (a management command, a unit test), the
getter returns the sentinel ``"-"``. It never raises, because a
caller that is not serving an HTTP request is a legitimate caller
that simply has no ID to read.

See docs/29-observability.md sections 6.
"""

from __future__ import annotations

from contextvars import ContextVar

# The HTTP header a caller may use to supply its own correlation ID.
# When the header is absent, the middleware generates one.
CORRELATION_ID_HEADER = "X-Correlation-ID"

# Returned by ``get_correlation_id`` when there is no value in scope.
NO_CORRELATION_ID = "-"

_correlation_id: ContextVar[str] = ContextVar(
    "correlation_id",
    default=NO_CORRELATION_ID,
)


def set_correlation_id(value: str) -> None:
    """Store ``value`` as the correlation ID for the current context."""
    _correlation_id.set(value)


def get_correlation_id() -> str:
    """
    Return the correlation ID for the current context.

    Returns ``NO_CORRELATION_ID`` (a single dash) when no ID has been
    set, which is the expected case outside an HTTP request.
    """
    return _correlation_id.get()


def reset_correlation_id() -> None:
    """
    Reset the correlation ID to its default.

    Called by the middleware on request teardown. Tests that set an ID
    and want to clean up also call this.
    """
    _correlation_id.set(NO_CORRELATION_ID)


__all__ = [
    "CORRELATION_ID_HEADER",
    "NO_CORRELATION_ID",
    "get_correlation_id",
    "reset_correlation_id",
    "set_correlation_id",
]
