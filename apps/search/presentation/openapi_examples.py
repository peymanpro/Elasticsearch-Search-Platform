"""
Curated OpenAPI examples.

Each constant in this module is a named request body that appears in
the generated OpenAPI schema and in Swagger UI's "Try it out" panel.
The examples come from the project's own business scenarios
(docs/01-business-scenario.md sections S1-S14), so they double as a
statement of what the platform is for.

The collection is deliberately small. Four examples for the search
endpoint, one example each for the others. Every search example
exercises a different capability; together they cover the search
surface.

See docs/25-openapi.md sections 4 and 6.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# POST /api/search/
# ---------------------------------------------------------------------------
# A plain full-text search. Uses default pagination and the default
# (relevance) sort. Demonstrates the platform's BM25 ranking plus the
# field boosts described in docs/14-relevance.md.
SEARCH_EXAMPLE_SIMPLE: dict[str, Any] = {
    "query": "wireless headphones",
}

# A search narrowed by category and price, sorted by price ascending.
# Demonstrates the filter DSL (docs/19-filtering-facets.md section 3)
# and business sorting (docs/20-sorting-pagination.md section 2.3).
SEARCH_EXAMPLE_FILTERED: dict[str, Any] = {
    "query": "monitor",
    "page": 1,
    "page_size": 10,
    "filters": {
        "category": "Electronics",
        "price_min": 100.0,
        "price_max": 500.0,
        "availability": "in_stock",
    },
    "sort": {"field": "price", "direction": "asc"},
}

# A search that also requests facet counts. Demonstrates the
# aggregation path (docs/19-filtering-facets.md sections 4 and 5) and
# the faceted navigation use case.
SEARCH_EXAMPLE_FACETED: dict[str, Any] = {
    "query": "wireless",
    "page_size": 20,
    "include_facets": True,
}

# A cursor-based search. Demonstrates the search_after pagination mode
# (docs/20-sorting-pagination.md section 4). The ``cursor`` value is a
# placeholder; a caller must supply the cursor returned by a prior
# response.
SEARCH_EXAMPLE_CURSOR: dict[str, Any] = {
    "query": "wireless",
    "page_size": 20,
    "cursor": [4.2, "SKU-1001"],
}


# ---------------------------------------------------------------------------
# POST /api/explain/
# ---------------------------------------------------------------------------
EXPLAIN_EXAMPLE: dict[str, Any] = {
    "query": "wireless headphones",
    "document_id": "SKU-1001",
}


# ---------------------------------------------------------------------------
# GET /api/suggest/
# ---------------------------------------------------------------------------
# The suggest endpoint takes query string parameters, so its example is
# declared as a parameter set rather than a body. The constant below
# gives the values the Swagger UI will prefill.
SUGGEST_EXAMPLE_QUERY = "headph"
SUGGEST_EXAMPLE_LIMIT = 5


__all__ = [
    "EXPLAIN_EXAMPLE",
    "SEARCH_EXAMPLE_CURSOR",
    "SEARCH_EXAMPLE_FACETED",
    "SEARCH_EXAMPLE_FILTERED",
    "SEARCH_EXAMPLE_SIMPLE",
    "SUGGEST_EXAMPLE_LIMIT",
    "SUGGEST_EXAMPLE_QUERY",
]
