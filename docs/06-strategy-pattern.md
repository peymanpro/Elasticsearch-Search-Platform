# The Strategy Pattern in This Project

## The Problem Being Solved

A search platform receives the same user request and can legitimately
prepare it in more than one way. Consider the query text:

    "  Mindray  uMEC 12  "

A literal search preserves the text and sends it to the search backend as
written (modulo the value object's outer-whitespace stripping, which is a
domain rule). A normalized search lowercases it and collapses the internal
whitespace before sending it. The two produce different texts, and -- for
a backend whose analyzers respond differently to casing or spacing --
potentially different results.

Both policies are correct. Which is right depends on what the caller is
doing. That is the definition of a Strategy problem.

## The Chosen Design

Three concepts, all in the domain layer as contracts, with implementations
in the application layer:

    SearchIntent              -- enum describing the caller's purpose
    SearchExecutionStrategy   -- Protocol: prepare and execute a search
    ProductSearchGateway      -- Protocol: execute a prepared search

The `SearchProductsUseCase` orchestrates:

    SearchProductsUseCase.execute(query, intent)
        -> select_strategy(intent)
        -> strategy.execute(query, gateway)
        -> SearchResults

## Why This Axis, and Not "Relevance Strategy"

The master roadmap places a much larger Strategy story in Phase 9
(relevance strategies: default, fuzzy, phrase-boosted, business-signal
weighted). That family is the substantial one. It is **not** implemented
here because:

- There is no index yet (Phase 6 creates it).
- There are no analyzers yet (Phase 7 defines them).
- There is no query builder yet (Phase 3.6 -- the very next sub-phase).
- There is no gateway implementation yet (Phase 3.7).

Building relevance strategies before any of those exist would mean
building against a nonexistent backend. The master prompt's Section 1.4
forbids abstraction for its own sake. Phase 3.5 therefore demonstrates the
Strategy pattern on a real axis (query preparation) whose implementations
are fully testable today and whose contract shape is what Phase 9 will
extend.

## Why This Design Satisfies the Open/Closed Principle

Adding a new strategy -- a `FuzzySearchStrategy`, a `PhraseAwareStrategy`,
a `SynonymsAwareStrategy` -- consists of:

1. Adding one class to `apps/search/application/strategies.py`.
2. Adding one entry to `_REGISTRY` in `apps/search/application/strategy_selector.py`.
3. Adding one member to `SearchIntent` in `apps/search/domain/strategies.py`.

No change is required to:
- `SearchProductsUseCase`
- any existing strategy
- any test that is not specifically about the new strategy
- the composition root's existing behaviour

This is the same property Phase 3.3 demonstrated for the cluster health
probe, now extended to a runtime-decision axis rather than a
compile-time-fixed one.

## Why This Design Satisfies the Liskov Substitution Principle

Any object that satisfies `SearchExecutionStrategy` structurally can be
substituted for any other. The use case calls only `execute`, and does
not inspect the strategy's identity beyond `name` for logging purposes.
No strategy is allowed to strengthen preconditions or weaken
postconditions relative to the Protocol:

- Input: a valid `SearchQuery` and a valid `ProductSearchGateway`.
- Output: a `SearchResults` value.
- Errors: strategies may propagate whatever the gateway raises; they do
  not swallow it. (Phase 23 will introduce a resilience policy at the
  boundary, but that policy is outside the strategy.)

## Why the Strategies Are Stateless

Both concrete strategies hold no per-request state. The registry in
`strategy_selector.py` therefore shares one instance of each strategy
across all requests. This is safe, allocates nothing per call, and makes
the strategies trivially testable. If a future strategy needs per-request
state (e.g. a per-request timeout budget), that strategy must acquire the
state via its `execute` arguments or be instantiated per request -- a
decision deferred to the phase that introduces the need.

## What This Document Does Not Decide

- Where the strategy selection happens *from* the HTTP layer (Phase 19).
- How the intent is derived from the user's request. At Phase 3.5 the
  intent is passed in by the caller. Phase 8's query builder and Phase
  9's relevance work may derive intent automatically; that is their
  decision, not this one's.
- How a gateway implementation is provided. Phase 3.7 introduces the
  adapter that satisfies `ProductSearchGateway`.
