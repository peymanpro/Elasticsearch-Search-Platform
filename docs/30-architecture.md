# Architecture

## 1. Purpose

This document describes the platform's architecture as built. It is
the reference for a reviewer who wants to understand the shape of the
codebase before reading any individual module. It covers Phase 25.1 of
the master roadmap.

The architecture was decided in Phase 2 and has been held stable since.
Every sub-phase since has fit inside the layers established there; no
layer has been added, removed, or inverted. That stability is the
claim this document makes.

## 2. The Four Layers

The application is a Django project organized as a single app
(`apps.search`) with four internal layers.

    Presentation
        |
        v
    Application
        |
        v
    Domain  <-- Infrastructure
        ^            |
        |            |
        +------------+
        (implements contracts)

**Presentation** translates HTTP to calls on the application layer
and renders results back to HTTP. It contains views, serializers,
URLs, the composition root, the correlation middleware, and the
exception handler.

**Application** coordinates use cases. It receives domain value
objects and returns domain results. It does not know which framework
or which search engine is behind it.

**Domain** defines the model (value objects), the rules that
constrain it, and the ports (contracts) that infrastructure must
satisfy. It has no imports of Django, DRF, or Elasticsearch.

**Infrastructure** contains the concrete adapters that satisfy the
domain's ports. It is the only layer that talks to Elasticsearch. It
imports the domain contracts and implements them.

## 3. The Dependency Rule

Dependencies point inward.

* Presentation depends on application, and (only from the composition
  root) on infrastructure.
* Application depends on domain.
* Domain depends on nothing else in the project.
* Infrastructure depends on domain.

The rule is enforced by
`tests/architecture/test_dependency_rules.py`, which parses each layer
with `ast` and fails if a forbidden import appears. The test is a
programmatic fact about the codebase, not a convention: a violation
cannot be merged without breaking the test suite.

The one sanctioned exception is the composition root
(`apps/search/presentation/composition.py`). It is the only file in
the presentation layer allowed to import the app's infrastructure
layer or the top-level Elasticsearch client package. The exception is
declared and documented inline in the test that enforces it.

## 4. Directory Layout

    Elasticsearch-Search-Platform/
    ??? config/                       Django project configuration
    ??? apps/search/
    ?   ??? domain/                   Value objects, ports, exceptions
    ?   ??? application/              Use cases, strategies, selectors
    ?   ??? infrastructure/           Adapters (Elasticsearch-backed)
    ?   ??? presentation/             Views, serializers, URLs, composition
    ?   ??? management/commands/      reindex, reindex_status
    ??? infrastructure/elasticsearch/ Managed Elasticsearch client
    ?   ??? client.py                 Lifecycle (get_client, reset)
    ?   ??? health.py                 ping, cluster_info, cluster_health
    ?   ??? documents.py              Single-document operations
    ?   ??? query/                    Clause vocabulary, query builder
    ?   ??? indices/                  Index settings, mapping, manager
    ?   ??? synonyms/                 Synonym list
    ??? infrastructure/datasets/      JSONL readers
    ??? data/                         Hand-authored dataset
    ??? benchmarks/                   Benchmark harness
    ??? docs/                         Design and architecture documents
    ??? tests/
        ??? unit/                     No cluster required
        ??? integration/              Cluster required
        ??? architecture/             Enforce layer rules

Two things are notable about this layout.

**The managed Elasticsearch client is at the top level, not inside
the app.** `infrastructure/elasticsearch/` is not a layer of the
search app; it is the transport that the app's infrastructure layer
adapts. Putting it inside `apps/search/infrastructure/` would suggest
it is an app-local concern; it is not.

**The domain and application layers are inside the app.** They are
app-specific model and rules, not general-purpose libraries. When the
project eventually grows a second app, the domain objects that should
be shared would migrate to a shared package.

## 5. The Composition Root

`apps/search/presentation/composition.py` is the only place that
answers the question "which concrete adapter satisfies this port?"
Its functions have the same shape:

    def build_<use_case>(<override>: <Port> | None = None) -> <UseCase>:
        resolved = override if override is not None else <ConcreteAdapter>()
        return <UseCase>(resolved)

In production, the caller passes nothing and gets the real adapter.
In tests, the caller passes a fake. The composition root does not
distinguish the two cases.

The composition root is the concrete realization of the Dependency
Inversion Principle in this codebase. Everything above it depends on
abstractions; the composition root is the one place where an
abstraction becomes a concrete class.

## 6. Ports and Adapters

Every collaboration between layers crosses a domain-defined port.
The ports in use today:

| Port | Implementations |
|---|---|
| `ClusterHealthProbe` | `ElasticsearchClusterHealthProbe`, `StaticReachabilityProbe` |
| `ProductSearchGateway` | `ElasticsearchProductSearchGateway` |
| `ProductFacetGateway` | `ElasticsearchFacetGateway` |
| `ProductSuggester` | `ElasticsearchProductSuggester` |
| `ProductExplainer` | `ElasticsearchProductExplainer` |
| `ProductIndexer` | `ElasticsearchBulkIndexer` |
| `RelevanceQueryComposer` | `RelevanceQueryBuilder` |
| `FuzzyQueryComposer` | `ElasticsearchFuzzyQueryComposer` |

All ports are `typing.Protocol` declarations. Adapters do not inherit
from them; they satisfy them by shape.

An interface-segregation test enforces that every port has at most
three public methods. A port with more is a signal that the contract
is serving more than one purpose and should be split.

## 7. The Search Path

A search request traverses the layers as follows.

    HTTP POST /api/search/
        |
        v
    apps.search.presentation.views.SearchView
        |  (validates the request via SearchRequestSerializer)
        |  (builds a SearchQuery from the request body)
        |
        v
    apps.search.presentation.composition.build_search_products_use_case()
        |  (chooses the concrete gateway and composer)
        |
        v
    apps.search.application.search_products.SearchProductsUseCase
        |  (selects a strategy for the request's intent)
        |
        v
    apps.search.application.strategies.RelevantSearchStrategy
        |  (asks the composer for a query)
        |  (asks the gateway to execute it)
        |
        v
    apps.search.infrastructure.relevance.RelevanceQueryBuilder
    apps.search.infrastructure.gateways.ElasticsearchProductSearchGateway
        |
        v
    infrastructure.elasticsearch.client.Elasticsearch
        |
        v
    Elasticsearch cluster

The reverse path (results) unwinds the same layers with a symmetrical
translation at each boundary. The presentation layer serializes the
result; the application layer never knows a serializer exists; the
domain layer never knows an HTTP response was produced.

## 8. Why This Architecture

The alternative ? a Django app where the view builds an Elasticsearch
query and parses the response ? is what most small search projects
look like. It is simpler to write for the first feature and worse for
every feature after.

This architecture was chosen because:

1. **The domain has rules that should not be re-implemented per
   view.** `Pagination`, `SearchQuery`, `ProductFilters`, `SortOrder`,
   `SuggestQuery`, and the other value objects enforce their
   invariants once. Every view benefits.
2. **The search engine should be replaceable.** The domain declares
   `ProductSearchGateway`; the platform implements it against
   Elasticsearch. A test can substitute a fake. A future migration to
   a different engine is a change to one adapter.
3. **The `_analyze`, `_search`, `_explain`, and `_bulk` APIs have
   different shapes.** Wrapping each in an adapter that translates
   between the domain's shape and the Elasticsearch shape means the
   call sites never juggle four different conventions.
4. **The tests want to exist at multiple levels.** Unit tests exercise
   domain rules without a cluster. Integration tests exercise the
   cluster through the same path the production code uses. The
   architecture makes both possible without contortion.

## 9. What Was Deliberately Not Done

* **No plugin or registry system.** The composition root is a set of
  explicit functions. A registry would be flexible in a way nothing
  needs.
* **No dependency injection framework.** Constructor parameters are
  the injection. A framework would add a layer of indirection over
  Python's own parameter passing.
* **No shared DTOs across layers.** Each layer has its own types. The
  presentation layer builds a dict for the serializer; the application
  layer returns a domain object; the domain returns a value object.
  Translating between them is a small cost paid once per boundary, in
  exchange for each layer being able to change its own shape without
  rippling.
* **No CQRS split.** Reads and writes are both present (search vs.
  indexing), but the read path and write path share no code and no
  state. A CQRS architecture would formalize that, at the cost of
  additional structure. The platform's write path is a management
  command and a few adapters; it does not warrant a command bus.

## 10. Related Documents

* `docs/00-project-identity.md` ? what the project is and is not.
* `docs/04-extension-points.md` ? the OCP posture.
* `docs/05-interface-segregation.md` ? the ISP policy.
* `docs/06-strategy-pattern.md`, `docs/07-builder-pattern.md` ?
  specific patterns used in the query path.
* `docs/08-pattern-review.md` ? the review that decided which patterns
  to keep.
* `docs/31-index-design.md` ? the physical index this architecture
  operates on.
* `docs/35-trade-offs.md` ? alternatives that were rejected.
