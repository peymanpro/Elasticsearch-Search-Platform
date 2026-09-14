"""
Domain-level exceptions.

These exceptions express violations of the domain's own rules. They are
raised when a value object would otherwise be constructed in an invalid
state. They are not HTTP errors and are not aware of any framework; the
presentation layer is responsible for translating them into status codes.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-layer errors."""


class InvalidSearchQueryError(DomainError):
    """Raised when a search query violates a domain invariant."""


class InvalidPaginationError(DomainError):
    """Raised when a pagination request violates a domain invariant."""
