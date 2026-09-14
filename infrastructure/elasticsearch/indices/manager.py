"""
Index lifecycle operations: create, delete, exists, refresh.

The manager consumes the settings and mapping JSON files through the
loader in this package's __init__. It does not know what an index
contains; it knows how to make one exist and not exist.

Phase 18 (reindexing and aliases) will extend this module. At Phase
5 the API is deliberately minimal:

    create_index(version)  -- create an index from the version's
                              settings and mapping
    delete_index(name)     -- remove an index
    index_exists(name)     -- is the index present?
    refresh_index(name)    -- make writes visible to search
"""

from __future__ import annotations

from typing import Any

from elasticsearch import RequestError
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.indices import load_mapping, load_settings


def physical_index_name(version: str) -> str:
    """
    Return the physical index name for a version.

    The convention is products-{version}. The unversioned name
    products is reserved for the alias (Phase 18). Keeping the
    version in the physical name is what lets a v2 index be built
    alongside a live v1 without collision.
    """
    return f"products-{version}"


_INDEX_ALREADY_EXISTS = "resource_already_exists_exception"


def create_index(version: str, *, ignore_existing: bool = False) -> dict[str, Any]:
    """
    Create the products index for a version.

    The index is created with the version's settings and mapping.
    If the index already exists:

        * with ignore_existing=False (default), the underlying
          RequestError propagates.
        * with ignore_existing=True, the call is a no-op and the
          function returns a dict reporting that the index already
          existed.

    Note: The Elasticsearch Python client raises RequestError (a
    subclass of BadRequestError) for a 400 status code. The specific
    error type string is "resource_already_exists_exception".
    """
    name = physical_index_name(version)
    settings = load_settings(version)
    mapping = load_mapping(version)

    try:
        return get_client().indices.create(
            index=name,
            settings=settings,
            mappings={
                "dynamic": mapping["dynamic"],
                "properties": mapping["properties"],
            },
        )
    except RequestError as exc:
        if not ignore_existing:
            raise
        error_type = str(getattr(exc, "error", ""))
        if _INDEX_ALREADY_EXISTS not in error_type:
            raise
        return {"acknowledged": True, "already_existed": True, "index": name}


def delete_index(name: str, *, ignore_missing: bool = True) -> dict[str, Any]:
    """
    Delete an index by its physical name.

    ignore_missing defaults to True: calling delete on an index
    that does not exist should be a no-op, not an error. This mirrors
    the idempotency the document delete operation already provides.
    """
    return get_client().indices.delete(index=name, ignore_unavailable=ignore_missing)


def index_exists(name: str) -> bool:
    """Return True if the index exists."""
    return bool(get_client().indices.exists(index=name))


def refresh_index(name: str) -> None:
    """
    Refresh an index so that recent writes are visible to search.

    The default refresh interval is one second; a test that indexes
    and immediately searches calls this to avoid waiting.
    """
    get_client().indices.refresh(index=name)


__all__ = [
    "create_index",
    "delete_index",
    "index_exists",
    "physical_index_name",
    "refresh_index",
]
