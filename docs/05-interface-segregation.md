# Interface Segregation Policy

## Purpose

This document records the Interface Segregation Principle (ISP) policy for
this project: what counts as a "port", what "narrow" means, and the
sanctioned way to make an exception. It is a companion to
`docs/04-extension-points.md`.

## The Principle in This Project

ISP says: no consumer should be forced to depend on methods it does not
use. A port that declares ten methods when a given consumer calls only two
of them forces that consumer to depend on eight methods of unused surface.
That is the violation.

## Scope: What Is a "Port" Here

A port is a `typing.Protocol` defined in `apps/search/domain/` (or a
submodule). Ports are the contracts that the domain offers to the
application layer and that infrastructure adapters satisfy.

Only these are subject to the ISP rules. The following are **not** ports
and are not subject to these rules:

- Django classes we use (`AppConfig`, `MiddlewareMixin`).
- DRF classes we use (`APIView`, `Serializer`).
- Concrete adapters in `apps/search/infrastructure/`.
- Value objects (`Pagination`, `SearchQuery`, `SearchResults`). These are
  data, not contracts; their methods describe the data, not a collaboration.

## The Current State (Phase 3.4)

There is **one** port in the codebase:

| Port | Methods | Consumer |
|---|---|---|
| `ClusterHealthProbe` | `is_reachable` | `GetServiceStatusUseCase` |

One method, one consumer, zero ISP violations. There is nothing to
segregate today, and no refactoring is performed "just in case". Inventing
a violation to fix would be a violation of the project's own rule against
abstractions without a concrete reason (master prompt, section 1.4).

What this phase does instead is make sure no ISP violation can be
introduced silently later.

## The Rule

Every domain port must have at most **three** public methods.

Three is not a magic number. It is chosen so that:

- A port with one or two methods is obviously focused; each consumer will
  use most of what it offers.
- A port with three methods is still narrow enough that a consumer
  reasonably needs all of them.
- A port with four or more methods is a signal to stop and ask whether the
  contract is really serving one purpose.

The number is a signal, not a law. When a port genuinely needs to be
wider, the sanctioned way to allow it is to add the port's fully qualified
name to `ALLOWED_WIDE_PORTS` in
`tests/architecture/test_interface_segregation.py`, together with a
one-line rationale explaining why the port cannot be split.

## What Happens When the Rule Fires

The test `test_every_domain_port_is_narrow` fails. The author has two
paths:

1. **Split the port.** This is preferred. The split is usually natural:
   two groups of methods serving two different kinds of consumer become
   two ports, each consumed independently. Both can be implemented by the
   same class if that is convenient; nothing in the ISP requires one
   class per protocol.

2. **Add an explicit exception.** When splitting is not possible because
   the methods truly belong together, the port is added to
   `ALLOWED_WIDE_PORTS` with a rationale. The rationale is reviewed as
   part of the commit that introduces it.

Both paths are honest. Silently raising `MAX_PUBLIC_METHODS_PER_PORT` is
not: the maximum is a policy value, and changing it is a policy change
that deserves the same deliberation as any other.

## Anticipated Ports

The following ports are expected to arrive in later phases. Their
introduction is subject to this policy.

| Expected port | Arrives in | Expected methods |
|---|---|---|
| `RelevanceStrategy` | Phase 9 | `apply`, maybe one comparison helper -- 1 or 2 |
| `QueryExecutor` (if introduced) | Phase 8 or 19 | `execute` -- 1 |
| `IndexLifecycleService` | Phase 18 | several operations; likely a service, not a port -- see below |
| `BatchPolicy` (if introduced) | Phase 17 | `chunks_for` -- 1 |

The `IndexLifecycleService` case is instructive: index lifecycle involves
create, reindex, alias switch, and rollback, which is four operations that
genuinely belong together operationally. If it becomes a port at all, it
will be a candidate for `ALLOWED_WIDE_PORTS` rather than a set of
artificially split interfaces. That decision is deferred to Phase 18.

## Exceptions Beyond the Domain

This policy applies to domain ports only. It does **not** apply to:

- The composition root's injection surface (a function signature, not a
  port).
- Concrete adapters (they may have as many private helpers as they need).
- The infrastructure layer's public surface (the Elasticsearch client
  itself is broad, but it is not our contract).

Those surfaces are governed by other rules in this project: Single
Responsibility for adapters, and the dependency rules enforced by
`tests/architecture/test_dependency_rules.py` for layering.
