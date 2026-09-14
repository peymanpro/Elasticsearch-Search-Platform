"""
Field vocabulary for the product document.

This module is the single source of truth for the names and semantics of
the product document fields. It is a vocabulary, not a data model: it
declares field names, value constraints, and purposes. It does not define
a Python class representing a full product document, because nothing yet
needs one. Phase 4.5 will introduce that class when it exists to be used.

The vocabulary is shared by the dataset generator (Phase 4.5), the index
mapping (Phase 6), analyzers (Phase 7), query composition (Phase 8),
relevance (Phase 9), aggregations (Phase 14), sorting (Phase 15), and
bulk indexing (Phase 17).

Centralising the names avoids the class of bug where "brand" in one module
becomes "manufacturer" in another. See docs/09-product-document-model.md
for the design rationale.

Nothing in this module imports Django, Django REST Framework, or the
Elasticsearch client. The architecture tests enforce this.
"""

from __future__ import annotations

from enum import StrEnum


class ProductField(StrEnum):
    """
    Names of the product document fields.

    Values are the exact strings used as JSON keys in the JSONL dataset
    and as field names in the Elasticsearch mapping. The enum is closed:
    adding a field means adding a member here and updating the design
    document in the same commit.
    """

    ID = "id"
    SKU = "sku"
    NAME = "name"
    BRAND = "brand"
    CATEGORY = "category"
    DESCRIPTION = "description"
    TAGS = "tags"
    SPECIFICATIONS = "specifications"
    LANGUAGE = "language"
    PRICE = "price"
    CURRENCY = "currency"
    RATING = "rating"
    AVAILABILITY = "availability"
    CREATED_AT = "created_at"
    POPULARITY = "popularity"


class ProductLanguage(StrEnum):
    """Language of the product text. English-only in the demonstration dataset."""

    ENGLISH = "en"


class Availability(StrEnum):
    """
    Coarse availability state of a product.

    A fixed set is used, rather than a free-text field, because
    availability is a filter and an aggregatable dimension (Phases
    14-15) where controlled vocabulary matters more than expressiveness.
    """

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    DISCONTINUED = "discontinued"


class Currency(StrEnum):
    """
    Currency of a product price.

    The demonstration dataset uses USD; the enum is closed so
    that typos cannot slip into the dataset unnoticed.
    """

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


# ---------------------------------------------------------------------------
# Purpose groups
# ---------------------------------------------------------------------------
# These frozensets describe what each field is for, not how it is mapped.
# The mapping decision (text vs keyword, analyzed vs not, boosted vs not)
# belongs to Phase 6 and Phase 7. What a field is for is a domain fact
# and belongs here.

TEXT_SEARCH_FIELDS: frozenset[ProductField] = frozenset(
    {
        ProductField.NAME,
        ProductField.BRAND,
        ProductField.CATEGORY,
        ProductField.DESCRIPTION,
        ProductField.TAGS,
    }
)
"""Fields that participate in full-text search and receive boosts."""


KEYWORD_FILTER_FIELDS: frozenset[ProductField] = frozenset(
    {
        ProductField.SKU,
        ProductField.BRAND,
        ProductField.CATEGORY,
        ProductField.LANGUAGE,
        ProductField.AVAILABILITY,
        ProductField.CURRENCY,
    }
)
"""Fields used in exact-match filters. No scoring impact."""


NUMERIC_RANGE_FIELDS: frozenset[ProductField] = frozenset(
    {
        ProductField.PRICE,
        ProductField.RATING,
        ProductField.POPULARITY,
    }
)
"""Fields that accept range filters and numeric aggregations."""


SORTABLE_FIELDS: frozenset[ProductField] = frozenset(
    {
        ProductField.PRICE,
        ProductField.RATING,
        ProductField.CREATED_AT,
        ProductField.POPULARITY,
    }
)
"""Fields usable in sort clauses."""


AGGREGATABLE_FIELDS: frozenset[ProductField] = frozenset(
    {
        ProductField.BRAND,
        ProductField.CATEGORY,
        ProductField.AVAILABILITY,
    }
)
"""Fields from which terms aggregations (facets) are produced."""


ALL_FIELDS: frozenset[ProductField] = frozenset(ProductField)
"""Every field declared in ProductField. Used for completeness checks."""


__all__ = [
    "AGGREGATABLE_FIELDS",
    "ALL_FIELDS",
    "Availability",
    "Currency",
    "KEYWORD_FILTER_FIELDS",
    "NUMERIC_RANGE_FIELDS",
    "ProductField",
    "ProductLanguage",
    "SORTABLE_FIELDS",
    "TEXT_SEARCH_FIELDS",
]
