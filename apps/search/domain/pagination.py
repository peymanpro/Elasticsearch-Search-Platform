"""
Pagination value object.

Expresses how much of a result set a caller is asking for, and where
in that result set to start. Two mechanisms are supported:

    * Offset-based pagination: ``Pagination(page=3, page_size=20)``.
      Simple; correct for any page depth within the offset window.
    * Cursor-based pagination: ``Pagination.from_cursor(cursor, page_size)``.
      Used when the result set may exceed the offset window, or when a
      caller wants stable pagination across concurrent writes.

The two are mutually exclusive. A Pagination constructed with a cursor
carries page=MISSING_PAGE internally and never computes an offset.

See docs/20-sorting-pagination.md sections 3 and 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.search.domain.exceptions import InvalidPaginationError

MIN_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100

# Elasticsearch's default max_result_window. Requests whose offset plus
# size exceeds this are rejected by the server. The domain rejects them
# first, so the caller gets a clear error before the network.
MAX_OFFSET_WINDOW = 10_000

# Sentinel for the page number of a cursor-based Pagination. It is
# deliberately out of range so that any accidental use of `.offset` on
# a cursor-based Pagination produces an error rather than a wrong value.
MISSING_PAGE = 0


@dataclass(frozen=True, slots=True)
class Pagination:
    """
    A request for a single page of results.

    Attributes:
        page: 1-based page number (offset-based). Ignored when cursor
            is set.
        page_size: Number of hits to return per page.
        cursor: When set, the sort values of the last hit on the
            previous page. The pagination is cursor-based; offset is
            not used. Default None (offset-based).

    Invariants:
        page >= MIN_PAGE (unless cursor is set)
        MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE
        For offset-based pagination, (page - 1) * page_size + page_size
            must not exceed MAX_OFFSET_WINDOW.
    """

    page: int = MIN_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    cursor: tuple[Any, ...] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.page_size < MIN_PAGE_SIZE or self.page_size > MAX_PAGE_SIZE:
            raise InvalidPaginationError(
                f"page_size must be between {MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}, "
                f"got {self.page_size}",
            )

        if self.cursor is not None:
            # Cursor-based pagination. The cursor must be a non-empty
            # tuple; an empty tuple would be rejected by Elasticsearch
            # and is meaningless.
            if len(self.cursor) == 0:
                raise InvalidPaginationError("cursor must not be empty")
            return

        # Offset-based pagination.
        if self.page < MIN_PAGE:
            raise InvalidPaginationError(
                f"page must be >= {MIN_PAGE}, got {self.page}",
            )

        if self.offset + self.page_size > MAX_OFFSET_WINDOW:
            raise InvalidPaginationError(
                f"page + page_size exceeds max_result_window "
                f"({MAX_OFFSET_WINDOW}); use cursor-based pagination "
                f"for deeper pages",
            )

    @classmethod
    def from_cursor(
        cls,
        cursor: tuple[Any, ...],
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Pagination:
        """
        Build a cursor-based Pagination.

        The cursor is the sort values of the last hit on the previous
        page. It is passed back to Elasticsearch unchanged.
        """
        return cls(page=MISSING_PAGE, page_size=page_size, cursor=cursor)

    @property
    def is_cursor_based(self) -> bool:
        """True if this pagination uses a cursor rather than an offset."""
        return self.cursor is not None

    @property
    def offset(self) -> int:
        """
        Zero-based offset of the first hit on this page.

        Raises:
            InvalidPaginationError: this pagination is cursor-based.
                A cursor-based request does not have an offset; asking
                for one is a programming error, and the failure is
                raised rather than silently returning a wrong value.
        """
        if self.cursor is not None:
            raise InvalidPaginationError("cursor-based pagination has no offset; use search_after")
        return (self.page - 1) * self.page_size
