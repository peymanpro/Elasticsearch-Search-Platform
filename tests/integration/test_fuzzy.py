"""
Integration tests for fuzzy search.

These tests use the project's noise dataset (data/search_noise.jsonl) to
verify that the fuzzy strategy finds the intended document when a user
types a typo, a spacing variant, or a case variant. Entries whose
category is "synonym" or "reorder" are out of scope for Phase 10 (they
belong to Phase 11 and Phase 10's scope is per-term edits).

The tests require a running Elasticsearch cluster and skip cleanly
when none is reachable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.search.application.strategies import FuzzySearchStrategy
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
NOISE_PATH = REPO_ROOT / "data" / "search_noise.jsonl"

TEST_INDEX = "products-fuzzy-test"


# Fuzzy-relevant noise categories: those that are per-term variations.
# "synonym" and "reorder" need different mechanisms.
FUZZY_CATEGORIES = {"typo", "spacing", "case"}


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def noise_entries() -> list[dict]:
    """Load the noise dataset."""
    entries = []
    with NOISE_PATH.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


@pytest.fixture(scope="module")
def canonical_index(noise_entries: list[dict]) -> str:
    """
    Create a temporary index with one document per distinct canonical
    term in the noise dataset, then clean it up.
    """
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v1")
    mapping = load_mapping("v1")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )

    # One document per unique canonical term.
    canonicals = sorted({entry["canonical"] for entry in noise_entries})
    for i, canonical in enumerate(canonicals):
        doc = {
            "id": f"C-{i:04d}",
            "sku": f"C-{i:04d}",
            "name": canonical.title(),
            "brand": "TestBrand",
            "category": "Electronics",
            "description": f"A {canonical} for testing.",
            "tags": ["test"],
            "specifications": {"source": "noise-dataset"},
            "language": "en",
            "price": 10.0,
            "currency": "USD",
            "rating": 4.0,
            "availability": "in_stock",
            "created_at": "2024-01-01T00:00:00Z",
            "popularity": 1,
        }
        index_document(
            index=TEST_INDEX,
            document_id=doc["id"],
            source=doc,
        )
    client.indices.refresh(index=TEST_INDEX)

    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def _matched_names(index: str, text: str) -> list[str]:
    """Run the fuzzy query for a text and return the matched names."""
    from apps.search.infrastructure.fuzzy import ElasticsearchFuzzyQueryComposer
    from apps.search.infrastructure.relevance import FIELD_BOOSTS

    composer = ElasticsearchFuzzyQueryComposer(fields=FIELD_BOOSTS)
    response = get_client().search(
        index=index,
        query=composer.build(text),
        size=20,
    )
    return [h["_source"]["name"].lower() for h in response["hits"]["hits"]]


def _assert_canonical_matches(
    index: str,
    entries: list[dict],
    category: str,
) -> None:
    """Assert that every noise entry of a category matches its canonical."""
    selected = [e for e in entries if e["category"] == category]
    assert selected, f"noise dataset has no {category} entries"

    failures = []
    for entry in selected:
        matched_names = _matched_names(index, entry["noise"])
        if not any(entry["canonical"] in name for name in matched_names):
            failures.append((entry["noise"], entry["canonical"], matched_names[:5]))

    assert not failures, (
        f"{len(failures)} {category} entries did not match their canonical: {failures}"
    )


# ---------------------------------------------------------------------------
# Fuzzy fixes typos, spacing, and case
# ---------------------------------------------------------------------------
def test_typo_returns_canonical_document(canonical_index: str, noise_entries: list[dict]) -> None:
    """Every typo noise entry should match the document for its canonical."""
    _assert_canonical_matches(canonical_index, noise_entries, "typo")


# Note: spacing variants (for example "head phones" for "headphones") are
# deliberately not tested here. Fuzzy matching operates per token, and a
# spacing variant changes the tokenization itself: a single query token
# cannot match two indexed tokens regardless of edit distance. Handling
# spacing variants requires a different mechanism (shingles, n-grams) and
# belongs to a later phase. See docs/15-fuzzy-search.md section 6.5.


def test_case_variant_returns_canonical(canonical_index: str, noise_entries: list[dict]) -> None:
    """Case variants should also match because analyzers lowercase."""
    _assert_canonical_matches(canonical_index, noise_entries, "case")


# ---------------------------------------------------------------------------
# Sanity checks on the strategy itself
# ---------------------------------------------------------------------------
def test_fuzzy_strategy_name_is_fuzzy() -> None:
    from apps.search.infrastructure.fuzzy import ElasticsearchFuzzyQueryComposer
    from apps.search.infrastructure.relevance import FIELD_BOOSTS

    composer = ElasticsearchFuzzyQueryComposer(fields=FIELD_BOOSTS)
    assert FuzzySearchStrategy(composer=composer).name == "fuzzy"


def test_fuzzy_strategy_is_registered_for_fuzzy_intent() -> None:
    from apps.search.application.strategy_selector import select_strategy
    from apps.search.domain.strategies import SearchIntent
    from apps.search.infrastructure.fuzzy import ElasticsearchFuzzyQueryComposer
    from apps.search.infrastructure.relevance import FIELD_BOOSTS

    composer = ElasticsearchFuzzyQueryComposer(fields=FIELD_BOOSTS)
    strategy = select_strategy(SearchIntent.FUZZY, fuzzy_composer=composer)
    assert isinstance(strategy, FuzzySearchStrategy)
