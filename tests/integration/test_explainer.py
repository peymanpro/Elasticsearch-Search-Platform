"""
Integration tests for explainability.

The tests index a small fixture catalog, compose the platform's
relevance query for a text, and explain specific (query, document)
pairs. They verify:

    * The explanation is a tree whose top-level node is a
      ScoreExplanation and whose children are also ScoreExplanation
      instances.
    * The description of at least one node mentions a field the
      platform boosts, so a reviewer can see the platform's policy in
      the explanation.
    * A non-matching document returns matched=False and
      explanation=None.

The tests skip cleanly when no cluster is reachable.
"""

from __future__ import annotations

import pytest

from apps.search.application.explain_score import ExplainScoreUseCase
from apps.search.domain.explanation import ExplainResult, ScoreExplanation
from apps.search.infrastructure.explainer import ElasticsearchProductExplainer
from apps.search.infrastructure.relevance import RelevanceQueryBuilder
from infrastructure.elasticsearch.client import get_client
from infrastructure.elasticsearch.documents import index_document
from infrastructure.elasticsearch.health import ping
from infrastructure.elasticsearch.indices import load_mapping, load_settings

pytestmark = pytest.mark.integration

TEST_INDEX = "products-explain-test"


FIXTURE_DOCUMENTS = [
    {
        "id": "E-001",
        "sku": "E-001",
        "name": "Wireless Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "A wireless product for audio.",
        "tags": ["wireless"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 349.99,
        "currency": "USD",
        "rating": 4.6,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 100,
    },
    {
        "id": "E-002",
        "sku": "E-002",
        "name": "Wired Studio Headphones",
        "brand": "Audio-Technica",
        "category": "Electronics",
        "description": "A wired product for studio work.",
        "tags": ["wired"],
        "specifications": {"color": "black"},
        "language": "en",
        "price": 149.00,
        "currency": "USD",
        "rating": 4.5,
        "availability": "in_stock",
        "created_at": "2024-01-01T00:00:00Z",
        "popularity": 50,
    },
]


@pytest.fixture(scope="module", autouse=True)
def _require_running_elasticsearch() -> None:
    if not ping():
        pytest.skip("Elasticsearch is not reachable.")


@pytest.fixture(scope="module")
def explain_index() -> str:
    client = get_client()
    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)

    settings = load_settings("v2")
    mapping = load_mapping("v2")
    client.indices.create(
        index=TEST_INDEX,
        settings=settings,
        mappings={"dynamic": mapping["dynamic"], "properties": mapping["properties"]},
    )

    for doc in FIXTURE_DOCUMENTS:
        index_document(index=TEST_INDEX, document_id=doc["id"], source=doc)
    client.indices.refresh(index=TEST_INDEX)

    try:
        yield TEST_INDEX
    finally:
        client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def _use_case(index: str) -> ExplainScoreUseCase:
    explainer = ElasticsearchProductExplainer(client=get_client(), index=index)
    composer = RelevanceQueryBuilder()
    return ExplainScoreUseCase(explainer=explainer, composer=composer)


# ---------------------------------------------------------------------------
# Structure of the explanation tree
# ---------------------------------------------------------------------------
def test_matching_document_returns_an_explanation(explain_index: str) -> None:
    result = _use_case(explain_index).execute("wireless headphones", "E-001")
    assert isinstance(result, ExplainResult)
    assert result.matched is True
    assert isinstance(result.explanation, ScoreExplanation)


def test_top_level_explanation_has_a_positive_score(explain_index: str) -> None:
    result = _use_case(explain_index).execute("wireless headphones", "E-001")
    assert result.explanation is not None
    assert result.explanation.value > 0


def test_explanation_has_children(explain_index: str) -> None:
    # The relevance query wraps a bool in a function_score; the top of
    # the explanation should have multiple children (the underlying
    # score plus each business signal).
    result = _use_case(explain_index).execute("wireless headphones", "E-001")
    assert result.explanation is not None
    assert result.explanation.details, "explanation tree has no children"
    assert all(isinstance(child, ScoreExplanation) for child in result.explanation.details)


def test_description_references_the_query(explain_index: str) -> None:
    result = _use_case(explain_index).execute("wireless headphones", "E-001")
    assert result.explanation is not None
    descriptions = _all_descriptions(result.explanation)
    joined = " ".join(descriptions).lower()
    assert "wireless" in joined or "headphones" in joined


def test_description_references_platform_policy(explain_index: str) -> None:
    # The relevance composer boosts name, brand, and so on. The
    # explanation should describe at least one field that the platform
    # boosts, so a reviewer can see the policy in the response.
    result = _use_case(explain_index).execute("wireless headphones", "E-001")
    assert result.explanation is not None
    descriptions = _all_descriptions(result.explanation)
    joined = " ".join(descriptions).lower()
    assert any(field in joined for field in ("name", "brand", "category", "description", "tags"))


def _all_descriptions(node: ScoreExplanation) -> list[str]:
    """Return every description in the tree, depth-first."""
    out = [node.description]
    for child in node.details:
        out.extend(_all_descriptions(child))
    return out


# ---------------------------------------------------------------------------
# Non-matching document
# ---------------------------------------------------------------------------
def test_non_matching_document_has_no_explanation(explain_index: str) -> None:
    # "wireless" does not match E-002's name ("Wired Studio Headphones")
    # in the must clause, so explain should return matched=False.
    result = _use_case(explain_index).execute("wireless", "E-002")
    assert result.matched is False
    assert result.explanation is None


# ---------------------------------------------------------------------------
# The use case composes the query itself
# ---------------------------------------------------------------------------
def test_use_case_composes_a_relevance_query(explain_index: str) -> None:
    # Running the use case for a document that does match the query
    # should produce an explanation; running it for a document that
    # does not should produce none. This is only true if the use case
    # actually composes a meaningful query (rather than sending an
    # empty one).
    #
    # The query is "wireless" specifically. E-001 has "wireless" in its
    # name; E-002 has only "wired". The multi_match uses OR semantics,
    # so a multi-word query like "wireless headphones" would match
    # E-002 on the "headphones" token; a single-term query on
    # "wireless" does not.
    use_case = _use_case(explain_index)
    matching = use_case.execute("wireless", "E-001")
    non_matching = use_case.execute("wireless", "E-002")
    assert matching.matched is True
    assert non_matching.matched is False
