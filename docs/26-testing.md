# Testing Strategy

## 1. Purpose

This document records what the project tests, how the test suite is
organized, and what is deliberately not tested. It covers the
roadmap sub-phases:

    * 21.1 -- Domain unit tests
    * 21.2 -- Query builder tests
    * 21.3 -- Analyzer tests
    * 21.4 -- Relevance tests
    * 21.5 -- Fuzzy / synonym tests
    * 21.6 -- Integration tests
    * 21.7 -- Index lifecycle tests
    * 21.8 -- Failure tests

## 2. Test Categories

Tests are organized into four directories:

| Directory | Marker | Needs Elasticsearch |
|---|---|---|
| tests/unit/ | none | no |
| tests/integration/ | integration | yes |
| tests/architecture/ | none | no |
| tests/ (root) | none | no |

The `integration` marker is declared in `pyproject.toml`. Tests
that require a running cluster are decorated with
`pytestmark = pytest.mark.integration` and skip cleanly when no
cluster is reachable (a module-scoped `_require_running_es`
fixture calls `ping()` and calls `pytest.skip` if it fails).

The marker lets a developer run the fast suite without a cluster:

    pytest -m "not integration"

## 3. Coverage by Sub-phase

### 3.1 Domain unit tests (21.1)

Files: `test_pagination.py`, `test_search_query.py`,
`test_search_result.py`, `test_service_status.py`,
`test_product_schema.py`, `test_product_document.py`,
`test_filters.py`, `test_facets.py`, `test_sorting.py`,
`test_indexing.py`, `test_suggest_query.py`.

Every domain value object has unit tests for:

* Default values and normal construction.
* Every documented invariant (rejection of invalid input).
* Immutability (frozen dataclass raises on assignment).
* Round-trip behavior where applicable (`ProductDocument`).

### 3.2 Query builder tests (21.2)

File: `test_query_builder.py`, `test_query_clauses.py`.

The builder is tested by asserting the *shape* of the generated
DSL, not just the API response. Every clause type has a test that
constructs it and compares the rendered dict against an expected
literal. The builder's invariants (no empty bool,
`minimum_should_match` alone is not a query) have dedicated tests.

### 3.3 Analyzer tests (21.3)

File: `test_analyzers.py` (integration).

Every custom analyzer is verified against a real cluster through
the `_analyze` API. The tests assert the exact token stream for
known inputs, including lowercase normalization, ASCII folding,
stopword removal, and stemming. An analyzer that is not verified
by a test in this file is not considered implemented.

### 3.4 Relevance tests (21.4)

File: `test_relevance.py` (integration).

The relevance tests use a fixture catalog designed to isolate each
mechanism: an exact-phrase match, a name-only match, a
description-only match, and a non-match. The tests assert ranking
order, not absolute scores: the score of a document is not a
stable contract, but its position relative to another document is
what the platform actually promises.

### 3.5 Fuzzy and synonym tests (21.5)

Files: `test_fuzzy.py`, `test_synonyms.py` (integration).

Fuzzy tests use the project's noise dataset
(`data/search_noise.jsonl`) to verify per-token typo tolerance.
The dataset categories that fuzzy addresses (typo, case) are
tested; the categories it does not address (spacing, reorder) are
documented as out of scope in `docs/15-fuzzy-search.md` section
6.5.

Synonym tests assert equivalence: two terms from the same synonym
group must return the same document set. This is a weaker
assertion than "the right documents come back," and it is
deliberately so: the platform's promise is that synonyms expand
the query, not that any specific document matches.

### 3.6 Integration tests (21.6)

Files: `test_query_dsl.py`, `test_filters.py`,
`test_facets_search.py`, `test_sorting_pagination.py`,
`test_highlighting.py`, `test_bulk_indexing.py`,
`test_suggester.py`, `test_explainer.py`, `test_search_api.py`.

Every HTTP endpoint and every query capability is exercised
through the layer it belongs to. The API tests use the DRF test
client; the query-level tests use the gateway directly.

### 3.7 Index lifecycle tests (21.7)

File: `test_reindex.py` (integration).

The lifecycle tests create two versions of a test index, verify
alias operations, run a full reindex, verify the alias switch, and
verify rollback. The reindex validation is tested by deliberately
triggering a failure and asserting that the alias did not switch.

### 3.8 Failure tests (21.8)

File: `test_failure_handling.py` (integration).

The failure tests exercise the platform's behavior when its
backend misbehaves:

* **Cluster unreachable.** The health endpoint returns
  `unhealthy` with a null alias target and a zero document count.
* **Missing index.** A search against an alias that does not
  resolve raises, and the exception handler translates it into a
  503 with the shaped error body.
* **Timeout.** A request-timeout from the client surfaces as a
  504 with the shaped error body.
* **Bulk partial failure.** A batch that contains an invalid
  document reports the failure count and the failure detail and
  does not lose the valid documents.

## 4. Test Doubles

The project uses hand-written test doubles rather than
`unittest.mock` wherever possible. Reasons:

* A hand-written fake is readable. Its behavior is visible in the
  test file, not scattered across `patch` decorators.
* It survives refactors. A `patch` that targets an internal name
  breaks when the name moves; a fake that implements a Protocol
  does not.
* The Protocol is the contract. A fake that satisfies it is a
  working implementation of the same interface; a `MagicMock` is a
  black box that happens to answer.

The exceptions where `patch` is used are places where the target
is a third-party class method (`Elasticsearch.ping`,
`Elasticsearch.cluster.health`) whose behavior cannot be replaced
by a fake without also replacing the client class. Those patches
are narrow and localized.

## 5. What is Deliberately Not Tested

* **Full ranking quality on a labeled corpus.** The platform has
  no labeled relevance judgments; ranking is tested for
  ordering properties on a hand-designed fixture, not for a mean
  average precision.
* **Latency percentiles.** Benchmarks (Phase 22) measure latency
  on defined workloads; the tests do not assert latency bounds
  because a slow CI environment would make them flaky.
* **Behavior under concurrent writes during reindex.** The
  platform has no concurrent writer; the design assumes a
  fixed dataset between the start and end of a reindex. This is
  documented in `docs/23-index-lifecycle.md` section 8.2.
* **Docker image correctness.** The image is validated by the
  Docker Compose startup itself; there is no test that asserts
  the image contains a specific file.
* **The Swagger UI rendering in a browser.** The schema tests
  assert the schema content; the rendering is a browser concern.

## 6. Running the Suite

    # Full suite (requires a running cluster)
    pytest

    # Unit and architecture tests only
    pytest -m "not integration"

    # Integration tests only
    pytest -m integration

    # A single file
    pytest tests/unit/test_filters.py

## 7. Rules for Tests

* A test that constructs domain objects asserts on domain
  behavior, not on implementation details.
* A test that exercises Elasticsearch asserts on the properties
  the platform promises; it does not assert absolute scores.
* A test that covers a public endpoint goes through the HTTP
  layer, not around it.
* A test that fails is either fixed (the code) or corrected (the
  test). It is never suppressed with a pytest.mark.skip that is
  not justified in a comment.
* When a test surfaces a defect, the defect is recorded and
  fixed; the test is not weakened to hide it. This has happened
  four times in the project's history and each incident is
  visible in the commit log.
