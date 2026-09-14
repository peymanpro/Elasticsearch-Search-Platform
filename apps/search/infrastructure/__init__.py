"""
Infrastructure layer.

Adapts the domain's contracts to concrete external systems. This is the
only place in the project that talks to Elasticsearch directly. Filled in
during Phase 2.4. The Elasticsearch client lifecycle itself lives under
the top-level ``infrastructure/`` package, where it was established in
Phase 1.4.
"""
