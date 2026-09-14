# The Builder Pattern in This Project

## The Problem Being Solved

Elasticsearch's query language is nested and rule-bearing. The canonical
composition for a filtered full-text search is a ``bool`` query with up
to four slots (``must``, ``filter``, ``should``, ``must_not``), each
holding a list of leaf clauses, each clause itself a nested mapping.

Constructing that structure by hand across many call sites produces:

- Repetition of the same nesting rules everywhere.
- Silent inconsistency (some queries get ``filter`` where they should
  get ``must``, or vice versa).
- An empty-``bool`` edge case that Elasticsearch rejects at request time
  rather than at construction time.
- Difficulty extending the query language: adding a new clause type
  today would require touching every call site that constructs it.

A builder addresses all four. It encapsulates the structural rules of
the language and leaves the semantic choices -- which fields, which
boosts, which relevance weighting -- to the caller.

## The Chosen Design

Two cooperating abstractions, both in `infrastructure/elasticsearch/query/`:

    Clause
      -- abstract base class for a leaf of the query language.
         Concrete subclasses: MatchClause, TermClause, RangeClause.
         Each clause renders itself as ``dict`` via ``to_dsl()``.

    QueryBuilder
      -- fluent accumulator for the four slots of a ``bool`` query.
         Renders the accumulated clauses via ``build()``.

Usage:

    query = (
        QueryBuilder()
        .must(MatchClause(field="name", value="monitor", boost=2.0))
        .filter(TermClause(field="brand", value="Mindray"))
        .filter(RangeClause(field="price", gte=500.0, lte=3000.0))
        .build()
    )

    # query ==
    # {
    #   "bool": {
    #     "must":   [{"match": {"name": {"query": "monitor", "boost": 2.0}}}],
    #     "filter": [
    #         {"term":  {"brand": "Mindray"}},
    #         {"range": {"price": {"gte": 500.0, "lte": 3000.0}}},
    #     ],
    #   }
    # }

## Why This Is a Real Builder, and Not Ceremony

A builder is justified when three conditions hold:

1. The object being built has structural rules that are easy to violate
   by hand. Elasticsearch's ``bool`` query qualifies: an empty ``bool``
   is invalid, and the four slots have different semantics (``filter``
   does not score, ``should`` does, ``must_not`` excludes).

2. Construction is naturally incremental. Queries are described a
   clause at a time, and the description reads more like the query than
   a nested dictionary would.

3. The set of building blocks (clauses) grows independently of the
   container (``bool``). The builder's API is stable across the
   vocabulary growth expected in Phases 8, 10, 11, and 12.

All three hold here.

## Why the Builder Does Not Know About the Domain

The builder is placed in `infrastructure/elasticsearch/query/`, not in
the domain or the application layer, and it knows nothing about products,
brands, prices, or relevance.

This is deliberate:

- Query-language construction is an infrastructure concern, not a domain
  concern. The domain talks in ``SearchQuery`` and ``SearchResults``; the
  builder is the adapter's tool for translating to and from Elasticsearch.

- Domain-aware query composition -- "search these fields, boost these,
  filter by those, apply this relevance strategy" -- is a distinct
  decision that belongs to the phase that introduces each concern. It is
  not the builder's responsibility to guess it.

The division is the same one the project has applied throughout: the
mechanism lives in infrastructure; the policy lives in the layer that
owns the requirement.

## What This Document Does Not Decide

- Which fields to search, in what order, with what weights. Phase 8.
- Which relevance strategy governs a given search. Phase 9.
- Which clauses to add for fuzzy, phrase, or synonym expansion.
  Phases 8, 10, 11.
- How the builder is called from the search gateway. Phase 3.7, next.
- How to translate a ``SearchQuery`` into a builder invocation. Phase 8.

Those decisions are deferred to the phases that introduce the concerns,
so that no policy is embedded here that later phases would need to
override.

## Tests

`tests/unit/test_query_builder.py` asserts the exact DSL fragment for
each slot, each combination, and each clause type. `tests/unit/test_query_clauses.py`
asserts each clause's rendering. Together, they document the current
contract in executable form. No Elasticsearch is contacted: the builder
is a pure Python mapping transformer and its tests are pure Python
assertions on that mapping.
