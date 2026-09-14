"""
Single-document operations against Elasticsearch.

Wraps the four fundamental document operations -- index (create or
replace), get, exists, delete -- against a named index. The bulk
variants and their failure handling are the subject of Phase 17 and
live in a separate module.

The functions here take and return plain dictionaries. The domain
object (ProductDocument) lives in the domain layer and is converted
at the boundary by the bulk indexer of Phase 17. Keeping this module
domain-agnostic means it can serve any index, not just products.

Functions propagate Elasticsearch errors. The operational resilience
policy that decides when to retry and when to fail is the subject of
Phase 23, not this module.
"""

from __future__ import annotations

from typing import Any

from infrastructure.elasticsearch.client import get_client


def index_document(
    *,
    index: str,
    document_id: str,
    source: dict[str, Any],
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Create or replace a document.

    ``PUT /<index>/_doc/<id>`` semantics: if the id does not exist,
    the document is created; if it exists, it is replaced. The
    response includes a ``result`` field equal to ``created`` or
    ``updated`` -- callers that care about which happened read it
    there.

    When ``refresh`` is True the write is made visible to search
    immediately. Callers use this in tests, where the default one-
    second refresh interval would make the next search miss the
    write.
    """
    return get_client().index(
        index=index,
        id=document_id,
        document=source,
        refresh="wait_for" if refresh else False,
    )


def get_document(
    *,
    index: str,
    document_id: str,
) -> dict[str, Any] | None:
    """
    Return a document's source, or None if it does not exist.

    Elasticsearch's ``get`` raises a 404 when the id is missing. The
    function converts that specific case into a None return, so that
    callers can express absence as a value rather than as an
    exception. Every other error propagates.
    """
    from elasticsearch import NotFoundError

    try:
        response = get_client().get(index=index, id=document_id)
    except NotFoundError:
        return None
    return response["_source"]


def document_exists(
    *,
    index: str,
    document_id: str,
) -> bool:
    """Return True if a document with the given id exists."""
    return bool(get_client().exists(index=index, id=document_id))


def delete_document(
    *,
    index: str,
    document_id: str,
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Delete a document.

    Deletion is idempotent: whether the document existed or not, the
    caller ends up in the same state. Elasticsearch itself returns
    HTTP 404 when the document is absent, and the Python client
    converts that into a NotFoundError by default. This function
    catches that specific case and returns a synthetic response with
    result=not_found so that callers need not distinguish "deleted
    something" from "nothing to delete".
    """
    from elasticsearch import NotFoundError

    try:
        return get_client().delete(
            index=index,
            id=document_id,
            refresh="wait_for" if refresh else False,
        )
    except NotFoundError:
        return {"result": "not_found", "_id": document_id, "_index": index}


__all__ = [
    "delete_document",
    "document_exists",
    "get_document",
    "index_document",
]
