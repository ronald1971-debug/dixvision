"""P3 — projection unification tests.

Pins the typed projection contracts added in the projection-unification
phase:

1. :class:`runtime.projections.CognitiveGovernanceProjection` — frozen
   dataclass shape matches the 13-guard cognitive integrity status.
2. :class:`runtime.projections.GovernanceProjection` — includes the new
   ``cognitive_integrity_healthy`` field with a ``True`` default.
3. :meth:`runtime.projections.ProjectionFactory.cognitive_governance` —
   produces a valid projection when the engine is available.
4. :meth:`ui.state_projection.StateProjection.cognitive_integrity` —
   returns a JSON-safe dict with ``available``, ``healthy``, ``detail``
   keys; safe-defaults when the kernel is not booted.
"""

from __future__ import annotations

import pytest

from runtime.projections import (
    CognitiveGovernanceProjection,
    GovernanceProjection,
)
from ui.state_projection import StateProjection


# ---------------------------------------------------------------------------
# CognitiveGovernanceProjection shape
# ---------------------------------------------------------------------------


def test_cogov_projection_is_frozen() -> None:
    p = CognitiveGovernanceProjection(
        overall_healthy=True,
        belief_integrity_ok=True,
        memory_clean=True,
        mutation_safe=True,
        no_hallucination=True,
        epistemic_current=True,
        learning_truthful=True,
        lineage_intact=True,
        identity_stable=True,
        no_synthetic_feedback=True,
        no_reward_hacking=True,
        causal_consistent=True,
        active_violations=(),
        detail="",
    )
    with pytest.raises((AttributeError, TypeError)):
        p.overall_healthy = False  # type: ignore[misc]


def test_cogov_projection_active_violations_is_tuple() -> None:
    p = CognitiveGovernanceProjection(
        overall_healthy=False,
        belief_integrity_ok=False,
        memory_clean=True,
        mutation_safe=True,
        no_hallucination=True,
        epistemic_current=True,
        learning_truthful=True,
        lineage_intact=True,
        identity_stable=True,
        no_synthetic_feedback=True,
        no_reward_hacking=True,
        causal_consistent=True,
        active_violations=("BELIEF_DRIFT",),
        detail="belief drift detected",
    )
    assert isinstance(p.active_violations, tuple)
    assert p.active_violations == ("BELIEF_DRIFT",)


def test_governance_projection_cognitive_integrity_field_default() -> None:
    """GovernanceProjection.cognitive_integrity_healthy defaults to True."""
    p = GovernanceProjection(
        system_mode="PAPER",
        health_score=1.0,
        active_hazards=(),
        live_execution_blocked=False,
        learning_active=True,
        evolution_active=True,
        operator_id="test",
        freeze_active=False,
    )
    assert p.cognitive_integrity_healthy is True


def test_governance_projection_cognitive_integrity_field_explicit() -> None:
    p = GovernanceProjection(
        system_mode="SAFE",
        health_score=0.0,
        active_hazards=("hazard_A",),
        live_execution_blocked=True,
        learning_active=False,
        evolution_active=False,
        operator_id="test",
        freeze_active=True,
        cognitive_integrity_healthy=False,
    )
    assert p.cognitive_integrity_healthy is False


# ---------------------------------------------------------------------------
# StateProjection.cognitive_integrity safe defaults
# ---------------------------------------------------------------------------


def test_state_projection_cognitive_integrity_no_kernel() -> None:
    """cognitive_integrity() returns a safe default when kernel not booted."""
    proj = StateProjection(kernel=None)
    ci = proj.cognitive_integrity()
    assert isinstance(ci, dict)
    assert "available" in ci
    assert "healthy" in ci
    assert "detail" in ci
    # When no kernel, cognitive_governance service is not registered
    assert ci["available"] is False
    assert ci["healthy"] is False


def test_state_projection_cognitive_integrity_keys() -> None:
    """cognitive_integrity() always returns the three expected keys."""
    proj = StateProjection(kernel=None)
    ci = proj.cognitive_integrity()
    assert set(ci.keys()) == {"available", "healthy", "detail"}


# ---------------------------------------------------------------------------
# ProjectionFactory.cognitive_governance integration
# ---------------------------------------------------------------------------


def test_projection_factory_cognitive_governance_produces_valid_projection() -> None:
    """ProjectionFactory.cognitive_governance() returns a valid projection."""
    from unittest.mock import MagicMock, patch

    from runtime.projections import ProjectionFactory

    mock_store = MagicMock()
    factory = ProjectionFactory(store=mock_store)

    # Patch the cognitive governance engine to return a known status
    mock_status = MagicMock()
    mock_status.overall_healthy = True
    mock_status.belief_integrity_ok = True
    mock_status.memory_clean = True
    mock_status.mutation_safe = True
    mock_status.no_hallucination = True
    mock_status.epistemic_current = True
    mock_status.learning_truthful = True
    mock_status.lineage_intact = True
    mock_status.identity_stable = True
    mock_status.no_synthetic_feedback = True
    mock_status.no_reward_hacking = True
    mock_status.causal_consistent = True
    mock_status.active_violations = []
    mock_status.detail = "ok"

    mock_engine = MagicMock()
    mock_engine.check_all.return_value = mock_status

    with patch("cognitive_governance.engine.get_cognitive_governance", return_value=mock_engine):
        proj = factory.cognitive_governance()

    assert isinstance(proj, CognitiveGovernanceProjection)
    assert proj.overall_healthy is True
    assert proj.active_violations == ()
    assert proj.detail == "ok"


def test_projection_factory_cognitive_governance_fallback_on_exception() -> None:
    """ProjectionFactory.cognitive_governance() falls back gracefully."""
    from unittest.mock import patch

    from runtime.projections import ProjectionFactory

    from unittest.mock import MagicMock
    mock_store = MagicMock()
    factory = ProjectionFactory(store=mock_store)

    with patch(
        "cognitive_governance.engine.get_cognitive_governance",
        side_effect=RuntimeError("engine not ready"),
    ):
        proj = factory.cognitive_governance()

    assert isinstance(proj, CognitiveGovernanceProjection)
    assert proj.overall_healthy is True  # safe default
    assert proj.detail == "unavailable"
