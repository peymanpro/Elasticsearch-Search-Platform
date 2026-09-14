"""
Sanity tests for the product field vocabulary.

These tests do not assert search behavior -- there is no search engine
involved. They assert that the vocabulary is internally coherent and
that the constants in code match the design document.
"""

from __future__ import annotations

from apps.search.domain.product_schema import (
    AGGREGATABLE_FIELDS,
    ALL_FIELDS,
    KEYWORD_FILTER_FIELDS,
    NUMERIC_RANGE_FIELDS,
    SORTABLE_FIELDS,
    TEXT_SEARCH_FIELDS,
    Availability,
    Currency,
    ProductField,
    ProductLanguage,
)


# ---------------------------------------------------------------------------
# Enum shape
# ---------------------------------------------------------------------------
def test_every_field_has_a_lowercase_snake_case_value() -> None:
    for field in ProductField:
        assert field.value == field.value.lower()
        assert " " not in field.value


def test_field_values_are_unique() -> None:
    values = [field.value for field in ProductField]
    assert len(values) == len(set(values))


def test_expected_core_fields_are_present() -> None:
    expected = {
        "id",
        "sku",
        "name",
        "brand",
        "category",
        "description",
        "tags",
        "specifications",
        "language",
        "price",
        "currency",
        "rating",
        "availability",
        "created_at",
        "popularity",
    }
    actual = {field.value for field in ProductField}
    assert actual == expected


def test_product_language_is_english_only() -> None:
    # The demonstration dataset is English-only. The enum remains as a
    # place to add further languages if the catalog ever becomes
    # multilingual, but today it contains exactly one member.
    assert {lang.value for lang in ProductLanguage} == {"en"}


def test_availability_is_a_closed_set() -> None:
    assert {a.value for a in Availability} == {
        "in_stock",
        "out_of_stock",
        "preorder",
        "discontinued",
    }


def test_currency_uses_upper_case_iso_codes() -> None:
    for currency in Currency:
        assert currency.value == currency.value.upper()
        assert len(currency.value) == 3


# ---------------------------------------------------------------------------
# Purpose groups
# ---------------------------------------------------------------------------
def test_purpose_groups_are_subsets_of_all_fields() -> None:
    groups = [
        TEXT_SEARCH_FIELDS,
        KEYWORD_FILTER_FIELDS,
        NUMERIC_RANGE_FIELDS,
        SORTABLE_FIELDS,
        AGGREGATABLE_FIELDS,
    ]
    for group in groups:
        assert group.issubset(ALL_FIELDS), f"{group} not a subset of ProductField"


def test_purpose_groups_are_non_empty() -> None:
    assert TEXT_SEARCH_FIELDS
    assert KEYWORD_FILTER_FIELDS
    assert NUMERIC_RANGE_FIELDS
    assert SORTABLE_FIELDS
    assert AGGREGATABLE_FIELDS


def test_all_fields_covers_every_product_field() -> None:
    assert frozenset(ProductField) == ALL_FIELDS


# ---------------------------------------------------------------------------
# Specific invariants from the design document (docs/09)
# ---------------------------------------------------------------------------
def test_name_is_searchable() -> None:
    assert ProductField.NAME in TEXT_SEARCH_FIELDS


def test_brand_is_searchable_filterable_and_aggregatable() -> None:
    assert ProductField.BRAND in TEXT_SEARCH_FIELDS
    assert ProductField.BRAND in KEYWORD_FILTER_FIELDS
    assert ProductField.BRAND in AGGREGATABLE_FIELDS


def test_price_is_numeric_and_sortable_but_not_a_keyword() -> None:
    assert ProductField.PRICE in NUMERIC_RANGE_FIELDS
    assert ProductField.PRICE in SORTABLE_FIELDS
    assert ProductField.PRICE not in KEYWORD_FILTER_FIELDS


def test_language_is_a_keyword_filter_but_not_searchable() -> None:
    assert ProductField.LANGUAGE in KEYWORD_FILTER_FIELDS
    assert ProductField.LANGUAGE not in TEXT_SEARCH_FIELDS


def test_id_is_not_in_any_purpose_group() -> None:
    groups = [
        TEXT_SEARCH_FIELDS,
        KEYWORD_FILTER_FIELDS,
        NUMERIC_RANGE_FIELDS,
        SORTABLE_FIELDS,
        AGGREGATABLE_FIELDS,
    ]
    for group in groups:
        assert ProductField.ID not in group
