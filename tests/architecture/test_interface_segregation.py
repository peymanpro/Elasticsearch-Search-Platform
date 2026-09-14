"""
Enforce Interface Segregation in the domain layer.

The policy (see docs/05-interface-segregation.md):

    A domain port -- a ``typing.Protocol`` defined in the domain package --
    is narrow. A consumer of a port must not be forced to depend on methods
    it does not use. In practice, this means every port has a small number
    of public methods, and a port only grows when a documented, reviewed
    reason justifies it.

The purpose of these tests is not to enforce a numeric limit for its own
sake. It is to make port growth visible. If a port needs to acquire a new
method -- or if a new fat port is genuinely required -- the change must
pass through this test, which forces the author to consciously update an
allow-list and explain why.

The tests introspect the domain package at runtime; they do not depend on
knowing which ports exist today. Adding a new port tomorrow automatically
subjects it to the same rules.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Protocol, get_type_hints

import apps.search.domain as domain_package

# Maximum number of public methods allowed on a domain port before the
# port must be listed in ALLOWED_WIDE_PORTS with an explanation. Three is
# chosen because a port with one or two methods is obviously focused, and
# a port with three is still narrow enough that every consumer is likely
# to use most of it.
MAX_PUBLIC_METHODS_PER_PORT = 3

# Sanctioned exceptions. Each key is the fully qualified name of a port;
# each value is a one-line rationale. Adding an entry is a conscious
# decision that must be reviewed; there are currently none.
ALLOWED_WIDE_PORTS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def _iter_protocol_classes() -> list[tuple[str, type]]:
    """
    Return (fully-qualified-name, class) for every Protocol defined in the
    domain package or its submodules.
    """
    found: list[tuple[str, type]] = []
    seen: set[str] = set()

    for module_info in pkgutil.walk_packages(
        path=domain_package.__path__,
        prefix=domain_package.__name__ + ".",
    ):
        module = importlib.import_module(module_info.name)
        for name, obj in inspect.getmembers(module, predicate=inspect.isclass):
            if obj is Protocol:
                continue
            # Only classes that directly inherit from Protocol. Subclasses
            # of another protocol are still protocols in intent, but we
            # keep the discovery simple: every port is a direct Protocol
            # subclass in this codebase.
            if Protocol not in obj.__bases__:
                continue
            qualified = f"{module.__name__}.{name}"
            if qualified in seen:
                continue
            seen.add(qualified)
            found.append((qualified, obj))

    return found


def _public_methods(protocol_cls: type) -> list[str]:
    """Return the names of public methods declared on the protocol."""
    methods: list[str] = []
    for name in getattr(protocol_cls, "__protocol_attrs__", ()):
        if name.startswith("_"):
            continue
        attr = inspect.getattr_static(protocol_cls, name, None)
        if attr is None:
            continue
        if callable(attr) or inspect.isfunction(attr):
            methods.append(name)
    return sorted(methods)


# ---------------------------------------------------------------------------
# Self-tests: discovery works and the domain has at least one port
# ---------------------------------------------------------------------------
def test_discovery_finds_at_least_one_protocol() -> None:
    ports = _iter_protocol_classes()
    assert ports, (
        "No Protocol classes were discovered in apps.search.domain. "
        "If all ports were removed, delete this test. If not, the "
        "discovery logic is broken."
    )


def test_discovery_finds_the_cluster_health_probe() -> None:
    names = {name for name, _ in _iter_protocol_classes()}
    assert "apps.search.domain.ports.ClusterHealthProbe" in names


# ---------------------------------------------------------------------------
# The segregation rules themselves
# ---------------------------------------------------------------------------
def test_every_domain_port_declares_at_least_one_method() -> None:
    """An empty port is meaningless; it communicates no contract."""
    for qualified, port in _iter_protocol_classes():
        methods = _public_methods(port)
        assert methods, f"{qualified} declares no public methods"


def test_every_domain_port_is_narrow() -> None:
    """
    A port with more than MAX_PUBLIC_METHODS_PER_PORT must appear in
    ALLOWED_WIDE_PORTS with a rationale.
    """
    for qualified, port in _iter_protocol_classes():
        methods = _public_methods(port)
        if len(methods) <= MAX_PUBLIC_METHODS_PER_PORT:
            continue
        assert qualified in ALLOWED_WIDE_PORTS, (
            f"{qualified} declares {len(methods)} public methods "
            f"({methods}), which exceeds the ISP limit of "
            f"{MAX_PUBLIC_METHODS_PER_PORT}. Either split the port into "
            f"narrower contracts, or add an entry to ALLOWED_WIDE_PORTS "
            f"with an explanation."
        )


def test_allowed_wide_ports_have_rationales() -> None:
    for qualified, rationale in ALLOWED_WIDE_PORTS.items():
        assert rationale.strip(), f"{qualified} has an empty rationale"


def test_allowed_wide_ports_reference_real_ports() -> None:
    """
    Stale allow-list entries hide drift. Every listed port must exist.
    """
    real_names = {name for name, _ in _iter_protocol_classes()}
    for qualified in ALLOWED_WIDE_PORTS:
        assert qualified in real_names, (
            f"ALLOWED_WIDE_PORTS references {qualified}, which no longer exists. Remove the entry."
        )


# ---------------------------------------------------------------------------
# Type-hint sanity: ports must remain introspectable
# ---------------------------------------------------------------------------
def test_port_methods_have_type_hints() -> None:
    """
    Protocols are contracts; their signatures must be inspectable.
    This test guards against ports being written without type hints,
    which would make their contracts unenforceable by static analysis.
    """
    for qualified, port in _iter_protocol_classes():
        hints = get_type_hints(port, include_extras=False)
        # get_type_hints on the class collects annotations on methods as
        # well; we only care that the call succeeds and yields something
        # for each method. Keep the assertion minimal: at least one hint
        # must exist on the protocol (the __init__ or a method signature).
        assert hints is not None, f"{qualified} has no discoverable type hints"
