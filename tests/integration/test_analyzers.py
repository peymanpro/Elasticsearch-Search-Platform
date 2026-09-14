"""
Integration tests for the custom analyzers.

These tests use the _analyze API to assert the exact token stream
each analyzer produces for known inputs. The analyzer is the only
thing between the raw text and the inverted index; if the tokens are
wrong, every query that relies on them is wrong.

The tests require a running Elasticsearch cluster. They create a
temporary index with the products-v1 settings, exercise _analyze
against its analyzers, and delete the index on teardown.
"""

from __future__ import annotations

import pytest

from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import (
    load_mapping,
    load_settings,
)

pytestmark = pytest.mark.integration

TEST_INDEX = "products-analyzer-test"


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def analyzer_index() -> str:
    """Create a temporary index carrying the analyzers, then clean up."""
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v1")
    mapping = load_mapping("v1")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )
    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def _tokens(index: str, analyzer: str, text: str) -> list[str]:
    """
    Return the tokens a named analyzer produces for a text.

    Uses the _analyze API with an explicit analyzer name. The analyzer
    must be defined in the index's analysis block; there is no need
    for the text to correspond to any document.
    """
    response = get_client().indices.analyze(
        index=index,
        analyzer=analyzer,
        text=text,
    )
    return [t["token"] for t in response["tokens"]]


# ---------------------------------------------------------------------------
# product_text_analyzer (name, description)
# ---------------------------------------------------------------------------
def test_text_analyzer_lowercases(analyzer_index: str) -> None:
    assert _tokens(analyzer_index, "product_text_analyzer", "Sony") == ["soni"]


def test_text_analyzer_stems_verbs_and_plurals(analyzer_index: str) -> None:
    tokens = _tokens(analyzer_index, "product_text_analyzer", "monitors monitoring monitored")
    assert tokens == ["monitor", "monitor", "monitor"]


def test_text_analyzer_removes_stopwords(analyzer_index: str) -> None:
    tokens = _tokens(
        analyzer_index, "product_text_analyzer", "the wireless headphones and a charger"
    )
    assert "the" not in tokens
    assert "and" not in tokens
    assert "a" not in tokens
    assert "headphon" in tokens or "headphones" in tokens
    assert "charger" in tokens


def test_text_analyzer_folds_accents(analyzer_index: str) -> None:
    # "caf? r?sum?" written with escapes so that this file stays ASCII.
    # Python interprets \\u00e9 as ? at runtime; the analyzer chain
    # lowercases, folds the accent to the plain letter, then stems.
    text = "caf" + chr(233) + " r" + chr(233) + "sum" + chr(233)
    tokens = _tokens(analyzer_index, "product_text_analyzer", text)
    assert tokens == ["cafe", "resum"]


def test_text_analyzer_is_deterministic(analyzer_index: str) -> None:
    input_text = "The Quick Brown Fox Jumps over the Lazy Dog"
    a = _tokens(analyzer_index, "product_text_analyzer", input_text)
    b = _tokens(analyzer_index, "product_text_analyzer", input_text)
    assert a == b


# ---------------------------------------------------------------------------
# product_keyword_analyzer (brand, category, tags)
# ---------------------------------------------------------------------------
def test_keyword_analyzer_lowercases(analyzer_index: str) -> None:
    assert _tokens(analyzer_index, "product_keyword_analyzer", "Sony") == ["sony"]


def test_keyword_analyzer_does_not_stem(analyzer_index: str) -> None:
    # Brand-like tokens must survive intact.
    assert _tokens(analyzer_index, "product_keyword_analyzer", "Sony") == ["sony"]
    assert _tokens(analyzer_index, "product_keyword_analyzer", "Books") == ["books"]


def test_keyword_analyzer_does_not_remove_stopwords(analyzer_index: str) -> None:
    # A category named "Home and Kitchen" keeps the word "and".
    tokens = _tokens(analyzer_index, "product_keyword_analyzer", "Home and Kitchen")
    assert tokens == ["home", "and", "kitchen"]


def test_keyword_analyzer_folds_accents(analyzer_index: str) -> None:
    # "M?ller" written with an escape so that this file stays ASCII.
    text = "M" + chr(252) + "ller"
    tokens = _tokens(analyzer_index, "product_keyword_analyzer", text)
    assert tokens == ["muller"]


# ---------------------------------------------------------------------------
# Symmetry between text and keyword analyzers
# ---------------------------------------------------------------------------
def test_both_analyzers_lowercase_and_fold_identically(analyzer_index: str) -> None:
    input_text = "Sony"
    text_tokens = _tokens(analyzer_index, "product_text_analyzer", input_text)
    keyword_tokens = _tokens(analyzer_index, "product_keyword_analyzer", input_text)
    # They differ in stemming, not in lowercasing or folding.
    assert keyword_tokens == ["sony"]
    assert text_tokens == ["soni"]  # porter_stem applied


# ---------------------------------------------------------------------------
# Analyzer is attached to the right fields
# ---------------------------------------------------------------------------
def test_name_field_uses_the_text_analyzer(analyzer_index: str) -> None:
    response = get_client().indices.analyze(
        index=analyzer_index,
        field="name",
        text="Monitors",
    )
    tokens = [t["token"] for t in response["tokens"]]
    assert tokens == ["monitor"]


def test_brand_field_uses_the_keyword_analyzer(analyzer_index: str) -> None:
    response = get_client().indices.analyze(
        index=analyzer_index,
        field="brand",
        text="Sony",
    )
    tokens = [t["token"] for t in response["tokens"]]
    assert tokens == ["sony"]
