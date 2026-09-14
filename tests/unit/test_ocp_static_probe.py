"""
Open/Closed Principle demonstration (Phase 3.3).

The flow being demonstrated:

    Existing Contract  ->  ClusterHealthProbe (domain port)
    New Strategy       ->  StaticReachabilityProbe (infrastructure)
    Extension without core modification
                       -> GetServiceStatusUseCase, ServiceRootView, and
                          every serializer remain untouched.

The tests below assert that a new adapter, wired through the *existing*
composition function, produces the *expected* observable behavior in the
*existing* view -- with no changes to any of those three components.
"""

from __future__ import annotations

from apps.search.application.get_service_status import GetServiceStatusUseCase
from apps.search.domain.ports import ClusterHealthProbe
from apps.search.domain.service_status import ServiceState
from apps.search.infrastructure.probes import StaticReachabilityProbe
from apps.search.presentation.composition import build_get_service_status_use_case


# ---------------------------------------------------------------------------
# The new strategy satisfies the existing contract
# ---------------------------------------------------------------------------
def test_static_probe_satisfies_the_existing_contract() -> None:
    # Structural typing means the class does not inherit from anything;
    # the domain's runtime-checkable Protocol is satisfied by shape alone.
    probe = StaticReachabilityProbe(reachable=True)
    assert isinstance(probe, ClusterHealthProbe)


# ---------------------------------------------------------------------------
# The existing composition function accepts the new strategy unchanged
# ---------------------------------------------------------------------------
def test_existing_composition_accepts_the_new_strategy() -> None:
    # build_get_service_status_use_case is unchanged. It accepts any object
    # that satisfies ClusterHealthProbe, including the new strategy.
    use_case = build_get_service_status_use_case(probe=StaticReachabilityProbe(True))
    assert isinstance(use_case, GetServiceStatusUseCase)


# ---------------------------------------------------------------------------
# The existing use case classifies the new strategy's output correctly
# ---------------------------------------------------------------------------
def test_use_case_classifies_static_probe_result_without_modification() -> None:
    healthy = build_get_service_status_use_case(probe=StaticReachabilityProbe(True))
    degraded = build_get_service_status_use_case(probe=StaticReachabilityProbe(False))

    assert healthy.execute().state is ServiceState.HEALTHY
    assert degraded.execute().state is ServiceState.DEGRADED


# ---------------------------------------------------------------------------
# The existing view reflects the new strategy through the existing path
# ---------------------------------------------------------------------------
def test_view_reflects_the_new_strategy_without_modification(monkeypatch) -> None:
    """
    The view is not touched. We redirect the composition call it makes to
    supply the new strategy, and the HTTP response changes accordingly.
    """
    from rest_framework.test import APIClient

    from apps.search.presentation import views as views_module

    def _build_degraded():
        return build_get_service_status_use_case(probe=StaticReachabilityProbe(False))

    monkeypatch.setattr(
        views_module,
        "build_get_service_status_use_case",
        _build_degraded,
    )

    response = APIClient().get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "elasticsearch-search-platform"
    assert payload["status"] == "degraded"
