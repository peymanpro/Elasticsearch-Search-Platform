# Pattern Review (Phase 3.8)

## Purpose

The master prompt (Section 1.5) states: "Design patterns only when
justified." Section 1.4 makes the corollary explicit: abstractions without
a concrete problem are removed.

This document is the formal review required by Phase 3.8. It enumerates
every design pattern and abstraction introduced in Phases 3.1-3.7, states
the problem each was meant to solve, and records a decision:
**keep / simplify / remove**. The review is conservative. Patterns that
are not pulling their weight are removed, not defended.

## The Three-Question Test

Every pattern reviewed here is evaluated against the same three questions:

1. Does the pattern solve a concrete, current problem?
2. Does at least one alternative implementation or runtime choice exist?
3. Would the code be worse without the pattern?

A pattern passes only if all three answers are yes.

## Patterns in Active Use

### P1 - Strategy (introduced Phase 3.5)

**Where:**

- `apps/search/domain/strategies.py` -- `SearchExecutionStrategy`
  Protocol, `SearchIntent` enum
- `apps/search/application/strategies.py` -- `LiteralSearchStrategy`,
  `NormalizedSearchStrategy`
- `apps/search/application/strategy_selector.py` -- registry and selector

**Problem it solves:** the same user query can be legitimately prepared
before reaching the search backend in more than one way. Preserving the
text verbatim is correct for brand names and model numbers; lowercasing
and collapsing whitespace is correct for free-text exploration. The
policy must be selectable.

**Test against the three questions:**

1. Concrete problem -- yes. The two strategies produce different
   observable text (`test_literal_strategy_preserves_text_verbatim` vs
   `test_normalized_strategy_lowercases_text`).
2. Runtime choice -- yes. `SearchIntent` is a caller-supplied parameter.
3. Worse without it -- yes. Without the strategies, the query
   preparation policy would be either hard-coded or scattered across
   call sites, and later phases (fuzzy, phrase, synonyms) would need to
   modify `SearchProductsUseCase` to add a new policy.

**Additional evidence:** adding a third strategy requires no change to
the use case, the selector's interface, or any existing strategy -- only
a new class and a new registry entry. This is the Open/Closed Principle
in action.

**Decision: Keep.**

### P2 - Builder (introduced Phase 3.6)

**Where:**

- `infrastructure/elasticsearch/query/clauses.py` -- `Clause` ABC and
  three concrete subclasses (`MatchClause`, `TermClause`, `RangeClause`)
- `infrastructure/elasticsearch/query/builder.py` -- `QueryBuilder`

**Problem it solves:** Elasticsearch `bool` queries have four slots
(`must`, `filter`, `should`, `must_not`) with structural rules. An empty
`bool` -- or one carrying only a `minimum_should_match` modifier -- is
rejected by the server. Hand-constructing these at every call site
produces silent inconsistency and defers the error to runtime.

**Test against the three questions:**

1. Concrete problem -- yes. The builder enforces two rules that would
   otherwise be enforced nowhere: no empty `bool`
   (`test_empty_builder_raises`), and `minimum_should_match` alone is
   not a query (`test_builder_with_only_minimum_should_match_still_raises`).
   Both tests exist and pass.
2. Runtime choice -- yes. The four slots are distinct semantic choices;
   a caller selects among them per query. Multiple clauses per slot
   accumulate in order.
3. Worse without it -- yes. Without the builder, the shape of a `bool`
   query would be reconstructed from dicts at every site, and any change
   to the shape (e.g. adding `minimum_should_match` handling) would
   ripple through every caller.

**Decision: Keep.**

### P3 - Adapter (introduced Phase 3.7)

**Where:**

- `apps/search/infrastructure/gateways.py` --
  `ElasticsearchProductSearchGateway`
- `apps/search/infrastructure/probes.py` --
  `ElasticsearchClusterHealthProbe`

**Problem it solves:** the domain defines contracts
(`ProductSearchGateway`, `ClusterHealthProbe`) that must be satisfied by
something that speaks Elasticsearch. The Elasticsearch client has a
different shape -- it takes query dictionaries and returns response
dictionaries -- and the domain layer must not import it (enforced by
`tests/architecture/test_dependency_rules.py`). An adapter translates
between the two.

**Test against the three questions:**

1. Concrete problem -- yes. Without the adapter, either the domain
   imports Elasticsearch (breaking the dependency rules) or the use
   cases embed Elasticsearch-specific logic.
2. Runtime choice -- yes. The composition root picks the adapter at
   startup; tests pick fakes; Phase 23 will pick a wrapped adapter with
   timeouts.
3. Worse without it -- yes. Layer independence would be lost.

**Decision: Keep.**

### P4 - Named Constructor (used by `SearchQuery.create`)

**Where:**

- `apps/search/domain/search_query.py` -- `SearchQuery.create`

**Problem it solves:** a `SearchQuery` must be constructed with a
stripped, validated text. Exposing `__init__` directly would allow
invalid instances to be created (empty text, whitespace-only text,
over-length text).

**Test against the three questions:**

1. Concrete problem -- yes. `test_create_strips_surrounding_whitespace`,
   `test_empty_text_is_rejected`, `test_whitespace_only_text_is_rejected`
   all pass.
2. Runtime choice -- no. There is one correct construction path. The
   alternative (a full factory) does not exist and is not needed.
3. Worse without it -- yes. Without the named constructor, callers could
   bypass validation.

The Named Constructor is a lightweight idiom, not a GoF pattern. It is
what makes the value object's invariants enforceable.

**Decision: Keep.**

## Patterns Evaluated and Deliberately Not Introduced

### P5 - Repository

Not present. The domain defines a `ProductSearchGateway` port, but its
scope is narrower than a Repository: it executes a single search and
returns a page of results. It does not represent a persistent collection.

**Reason not to introduce:** a Repository would be a second abstraction
over the same concern (accessing the products catalog) without a second
concrete behavior to justify it. Section 1.4 of the master prompt is
explicit about not doing this.

**Decision: Do not introduce.**

### P6 - Specification

Not present. The Query Builder composes clauses, which is the
domain-appropriate way to express "these things must be true about a
document." The four slots of a `bool` query are the composition
mechanism.

**Reason not to introduce:** a Specification layer over the top of the
builder would be ceremony. The builder already provides composition; a
second composition mechanism would only obscure which one is
authoritative.

**Decision: Do not introduce.**

### P7 - Factory (GoF)

Not present. `strategy_selector.select_strategy` is a lookup table over
pre-constructed stateless strategies, not a factory. It does not
construct instances per request.

**Reason not to introduce:** a GoF Factory would add a construction
indirection with no construction to abstract. If a future strategy
acquires per-request state (see `docs/06-strategy-pattern.md`), that
becomes a design conversation for the phase that introduces the need.
Not today.

**Decision: Do not introduce.**

## Findings: Simplifications Applied

The review identified one piece of dead code that did not pull its
weight:

- **`apps/search/application/strategies.py`** contained a line of the
  form `_ = Pagination  # keep the import meaningful ...`. The
  `Pagination` import existed only to satisfy an unused-import concern;
  the underscore assignment was a workaround. Neither the import nor the
  assignment served a purpose. The correct action was to remove both.

**Action taken:** the import and the underscore assignment are removed
in the commit that accompanies this review.

## Findings: Kept as Written

- `Clause` is an ABC, not a `Protocol`. An ABC is appropriate here
  because the clause family is closed (base class and subclasses live in
  one file) and `to_dsl()` is a shared method every subclass implements.
  A Protocol would also work but would document intent less directly.

- `ServiceState` is a `StrEnum`, not a plain `str`. The enum expresses a
  closed set of states; using a string would lose type safety at no
  benefit.

- The domain ports (`ClusterHealthProbe`, `ProductSearchGateway`,
  `SearchExecutionStrategy`) use `typing.Protocol` rather than ABCs.
  This matches the convention recorded in `docs/04-extension-points.md`
  and allows adapters to satisfy the contracts structurally without
  inheriting from anything.

## Summary Table

| Pattern | Status | Decision |
|---|---|---|
| Strategy | In active use | Keep |
| Builder | In active use | Keep |
| Adapter | In active use | Keep |
| Named Constructor | In active use | Keep |
| Repository | Not introduced | Defer indefinitely |
| Specification | Not introduced | Defer indefinitely |
| Factory (GoF) | Not introduced | Defer until per-request construction exists |

Three patterns are in active use. Four idioms or patterns were evaluated.
One piece of dead code was removed. No new patterns were introduced to
"complete" the review.

## Rule for the Future

Any pattern introduced after this review must be justified in the commit
that introduces it, and must pass the same three-question test used here.
If any question is answered "no", the pattern is not introduced.

The review is repeated at the next major milestone (Phase 9, where the
substantial relevance-strategy family arrives) rather than on a fixed
schedule.
