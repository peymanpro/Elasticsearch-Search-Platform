"""
Logging filter that injects the correlation ID into every log record.

The Django logging configuration references this filter in the
formatter; see docs/29-observability.md section 8. The filter reads
the correlation ID from
``apps.search.presentation.correlation.get_correlation_id`` and
attaches it as ``record.correlation_id``. The formatter then formats
it as part of the line.

The filter has no configuration and no side effects. It exists so
that the format string can reference a field that standard log
records do not carry.
"""

from __future__ import annotations

import logging

from apps.search.presentation.correlation import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    """Attach the current correlation ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


__all__ = ["CorrelationIdFilter"]
