"""
Pagination value object.

Expresses how much of a result set a caller is asking for. The rules for
what constitutes a valid page and page size are domain invariants: they
are true regardless of which search engine or HTTP framework sits behind
the domain.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.domain.exceptions import InvalidPaginationError

MIN_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class Pagination:
    """
    A request for a single page of results.

    Attributes:
        page: 1-based page number.
        page_size: Number of hits to return per page.

    Invariants:
        page >= MIN_PAGE
        MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE
    """

    page: int = MIN_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        if self.page < MIN_PAGE:
            raise InvalidPaginationError(
                f"page must be >= {MIN_PAGE}, got {self.page}",
            )
        if self.page_size < MIN_PAGE_SIZE or self.page_size > MAX_PAGE_SIZE:
            raise InvalidPaginationError(
                f"page_size must be between {MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}, "
                f"got {self.page_size}",
            )

    @property
    def offset(self) -> int:
        """Zero-based offset of the first hit on this page."""
        return (self.page - 1) * self.page_size
