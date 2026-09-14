"""
Index lifecycle operations: create, delete, exists, refresh, aliases.

The manager consumes the settings and mapping JSON files through the
loader in this package's __init__. It does not know what an index
contains; it knows how to make one exist, make one not exist, and
point an alias at one.

Alias operations are the platform's mechanism for zero-downtime index
switches. The `switch_alias` operation issues a single `_aliases`
request that removes the alias from the current index and adds it to
the new one atomically. See docs/23-index-lifecycle.md sections 4 and
6.
"""

from __future__ import annotations

from typing import Any

from elasticsearch import NotFoundError, RequestError
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.indices import (
    INDEX_ALIAS,
    load_mapping,
    load_settings,
)


def physical_index_name(version: str) -> str:
    """
    Return the physical index name for a version.

    The convention is products-{version}. The unversioned name
    products is reserved for the alias. Keeping the version in the
    physical name is what lets a v2 index be built alongside a live
    v1 without collision.
    """
    return f"products-{version}"


def create_index(version: str, *, ignore_existing: bool = False) -> dict[str, Any]:
    """
    Create the products index for a version.

    The index is created with the version's settings and mapping.
    If the index already exists:

        * with ``ignore_existing=False`` (default), the underlying
          RequestError propagates.
        * with ``ignore_existing=True``, the call is a no-op and the
          function returns a dict reporting that the index already
          existed.

    Note: ``ignore_unavailable`` is an Elasticsearch parameter on the
    delete and search APIs, not on create. Passing it to create is a
    client-side TypeError. The correct "idempotent create" pattern is
    the exception handling below.
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
        if "resource_already_exists_exception" not in error_type:
            raise
        return {"acknowledged": True, "already_existed": True, "index": name}


def delete_index(name: str, *, ignore_missing: bool = True) -> dict[str, Any]:
    """
    Delete an index by its physical name.

    ``ignore_missing`` defaults to True: calling delete on an index
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


# ---------------------------------------------------------------------------
# Alias operations
# ---------------------------------------------------------------------------
def alias_exists(alias: str = INDEX_ALIAS) -> bool:
    """Return True if the alias exists."""
    return bool(get_client().indices.exists_alias(name=alias))


def get_alias_target(alias: str = INDEX_ALIAS) -> str | None:
    """
    Return the physical index the alias currently points at, or None.

    The platform's alias is exclusive: it points at exactly one index
    (docs/23-index-lifecycle.md section 4.3). If the alias is missing,
    None is returned. If the alias somehow points at multiple indices,
    the first one is returned; the caller is expected to have kept the
    alias exclusive via the switch operation.
    """
    try:
        response = get_client().indices.get_alias(name=alias)
    except NotFoundError:
        return None
    for index_name in response:
        return index_name
    return None


def attach_alias(
    version: str,
    alias: str = INDEX_ALIAS,
) -> dict[str, Any]:
    """
    Attach the alias to a physical index.

    This is a one-sided operation: the alias is added to the index.
    Used for the initial creation of an alias, not for switching
    between indices. For switching, use ``switch_alias``.
    """
    name = physical_index_name(version)
    return get_client().indices.put_alias(index=name, name=alias)


def switch_alias(
    new_version: str,
    alias: str = INDEX_ALIAS,
) -> dict[str, Any]:
    """
    Point the alias at a new physical index, atomically.

    Removes the alias from whatever index currently holds it and adds
    it to the new index, in one `_aliases` request. Elasticsearch
    guarantees the request is atomic: the alias never points at
    neither index and never points at both.

    Raises:
        ValueError: no alias currently exists to switch. This is a
            programming error: switching an alias that does not yet
            exist is a lifecycle bug, not a runtime condition.
    """
    current_target = get_alias_target(alias)
    if current_target is None:
        raise ValueError(
            f"alias {alias!r} does not currently point at any index; use attach_alias to create it"
        )

    new_target = physical_index_name(new_version)
    return get_client().indices.update_aliases(
        actions=[
            {"remove": {"index": current_target, "alias": alias}},
            {"add": {"index": new_target, "alias": alias}},
        ]
    )


def rollback_alias(
    previous_version: str,
    alias: str = INDEX_ALIAS,
) -> dict[str, Any]:
    """
    Point the alias back at a previous physical index, atomically.

    Semantically identical to ``switch_alias`` but named to make the
    intent explicit at the call site. See docs/23-index-lifecycle.md
    section 7.
    """
    return switch_alias(previous_version, alias=alias)


__all__ = [
    "alias_exists",
    "attach_alias",
    "create_index",
    "delete_index",
    "get_alias_target",
    "index_exists",
    "physical_index_name",
    "refresh_index",
    "rollback_alias",
    "switch_alias",
]
