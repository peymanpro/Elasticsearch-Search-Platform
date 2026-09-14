"""
Unit tests for the composition root.

These tests demonstrate the Dependency Inversion Principle at the
composition boundary. The use case depends on the ``ClusterHealthProbe``
Protocol; the composition root is the only place where a concrete adapter
is chosen; and the choice is parameterised so that tests can inject a fake
without patching.

The proof of inversion is direct: two different probes, injected through
the same composition function, produce two different observable outcomes
in the use case's result, with no change to the use case itself.
"""

from __future__ import annotations

from apps.search.domain.service_status import ServiceState
from apps.search.infrastructure.probes import ElasticsearchClusterHealthProbe
from apps.search.presentation.composition import build_get_service_status_use_case


class _FakeProbe:
    """Test double that satisfies the ClusterHealthProbe Protocol."""

    def __init__(self, reachable: bool) -> None:
        self._reachable = reachable
        self.calls = 0

    def is_reachable(self) -> bool:
        self.calls += 1
        return self._reachable


# ---------------------------------------------------------------------------
# Default production path
# ---------------------------------------------------------------------------
def test_default_composition_uses_the_real_adapter() -> None:
    use_case = build_get_service_status_use_case()
    # Reach into the use case to inspect the wired dependency. This is a
    # deliberate introspection; the alternative would be to contact
    # Elasticsearch, which this unit test must not require.
    adapter = use_case._cluster_health_probe
    assert isinstance(adapter, ElasticsearchClusterHealthProbe)


# ---------------------------------------------------------------------------
# Injection path -- the DIP demonstration
# ---------------------------------------------------------------------------
def test_injected_reachable_probe_produces_healthy_state() -> None:
    fake = _FakeProbe(reachable=True)
    use_case = build_get_service_status_use_case(probe=fake)

    status = use_case.execute()

    assert status.state is ServiceState.HEALTHY
    assert fake.calls == 1


def test_injected_unreachable_probe_produces_degraded_state() -> None:
    fake = _FakeProbe(reachable=False)
    use_case = build_get_service_status_use_case(probe=fake)

    status = use_case.execute()

    assert status.state is ServiceState.DEGRADED
    assert fake.calls == 1


def test_swapping_the_adapter_swaps_the_observable_behaviour() -> None:
    # Two different adapters, same composition function, two different
    # results. Nothing about the use case changed. This is dependency
    # inversion made observable.
    healthy_use_case = build_get_service_status_use_case(probe=_FakeProbe(True))
    degraded_use_case = build_get_service_status_use_case(probe=_FakeProbe(False))

    assert healthy_use_case.execute().state is ServiceState.HEALTHY
    assert degraded_use_case.execute().state is ServiceState.DEGRADED


# ---------------------------------------------------------------------------
# The view is agnostic of which adapter was injected
# ---------------------------------------------------------------------------
def test_service_root_view_does_not_care_which_adapter_is_wired(monkeypatch) -> None:
    """
    Drive the view with a fake adapter without touching Elasticsearch.

    The view calls ``build_get_service_status_use_case()`` with no
    arguments -- the production signature. We monkeypatch that call in the
    view module to a lambda that supplies our fake, so the end-to-end
    behaviour of the view is exercised without the composition root
    needing an injection point at the view layer.
    """
    from rest_framework.test import APIClient

    from apps.search.presentation import views as views_module

    def fake_builder():
        return build_get_service_status_use_case(probe=_FakeProbe(True))

    monkeypatch.setattr(views_module, "build_get_service_status_use_case", fake_builder)

    response = APIClient().get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
