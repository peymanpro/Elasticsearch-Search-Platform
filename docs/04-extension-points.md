# Extension Points and the Open/Closed Principle

## Purpose

This document records *where* the Open/Closed Principle currently applies in
this project, and *where* it is expected to apply as later phases introduce
the substantial extension axes. It exists so that future extension decisions
are checked against a written policy rather than invented ad hoc.

The Open/Closed Principle is only meaningful when there is a concrete
variation axis. This document is therefore written in a spirit of restraint:
it lists what exists, what is coming, and what is deliberately *not* being
built today.

## What OCP Means in This Project

A component is "open for extension" here when a new implementation of a
contract can be added without modifying:

* the contract itself,
* any existing consumer of the contract,
* any existing test that was not specifically about the new implementation.

A component is "closed for modification" when the code paths that consume it
do not need to change to accommodate new implementations.

The mechanism used throughout is **structural typing via `typing.Protocol`**.
Adapters do not inherit from a base class; they satisfy a shape. Adding a new
adapter therefore does not touch the definition of the contract.

## Current Extension Points

### EP-1: `ClusterHealthProbe` (domain port)

Defined in `apps/search/domain/ports.py`. Consumers: `GetServiceStatusUseCase`.
Implementations today:

| Implementation | Module | Purpose |
|---|---|---|
| `ElasticsearchClusterHealthProbe` | `apps/search/infrastructure/probes.py` | Production adapter backed by the managed Elasticsearch client |
| `StaticReachabilityProbe` | `apps/search/infrastructure/probes.py` | Fixed-state strategy for failure simulation and operational tests |

Adding `StaticReachabilityProbe` in Phase 3.3 required **no modification** to:
* the `ClusterHealthProbe` Protocol,
* the `GetServiceStatusUseCase` class,
* the `ServiceRootView` class,
* any serializer.

That is the demonstration of OCP at this scale.

### EP-2: The composition root

Defined in `apps/search/presentation/composition.py`. Its single
responsibility is to choose which concrete adapter is wired into which use
case. Its `probe` parameter is the injection seam.

## Extension Points Expected in Later Phases

The following extension axes are anticipated by the roadmap and are recorded
here so that the pattern they will follow is clear before they arrive. None
of them are implemented today.

| Expected extension point | Arrives in | Expected shape |
|---|---|---|
| Analyzer variants (English, Persian, custom) | Phase 7 | Analyzer definitions, not Python classes; extension is at the index-settings level |
| Query builder strategies (match, multi_match, bool composition) | Phase 8 | A builder that composes clauses; extension via added builder methods rather than new strategies |
| Relevance strategies (default, fuzzy, phrase-boosted, business-signal weighted) | Phase 9 | A `RelevanceStrategy` Protocol with concrete strategies selected per query intent |
| Indexing batch strategies (small/medium/large) | Phase 17 | A batching policy that can be swapped based on dataset size |
| Index lifecycle actions (create, reindex, alias switch, rollback) | Phase 18 | A lifecycle service with distinct operation methods |

**The relevance strategies of Phase 9 are the substantial OCP story for this
project.** That is where multiple implementations of a single contract will
coexist and where the choice between them becomes a runtime decision rather
than a compile-time one.

## What This Project Deliberately Does Not Do

The following are excluded because they are ceremony without a problem to
solve at the present scale:

* **Plugin registries** -- there is no requirement to discover implementations
  dynamically. Composition is explicit and testable as written.
* **Abstract base classes for adapters** -- Protocols are sufficient and avoid
  a false hierarchy.
* **Strategy interfaces without two or more concrete strategies** -- an
  interface with a single implementation is not an extension point; it is
  premature abstraction.

## Rule for Adding a New Extension Point

A new Protocol (or other OCP mechanism) may be introduced when **all** of the
following hold:

1. At least two concrete implementations are expected within the phases
   covered by the roadmap.
2. The selection between implementations is genuinely a runtime decision, not
   a compile-time constant.
3. The abstraction lives in the domain or application layer, and the
   implementations live in infrastructure.

When only one implementation exists and the selection is fixed, the
implementation is used directly. This is the honest application of the
principle.
