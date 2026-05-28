"""Tests for runtime authority (CONVERGENCE PILLAR 1).

Covers:
- RuntimeSnapshot immutability
- RuntimeAuthorityStore read/write
- WriterToken authorization
- Projections
- Subscriptions
"""

from __future__ import annotations


def test_snapshot_is_frozen():
    """RuntimeSnapshot is immutable."""
    from runtime.authority import RuntimeSnapshot

    snap = RuntimeSnapshot()
    try:
        snap.version = 99  # type: ignore[misc]
        raise AssertionError("Should not reach here")
    except Exception:
        pass


def test_store_initial_state():
    """Store starts with version 0 and default operator authority."""
    from runtime.authority import RuntimeAuthorityStore

    store = RuntimeAuthorityStore()
    assert store.version == 0
    assert store.snapshot.system_mode == "PAPER"
    assert store.snapshot.live_execution_blocked is True


def test_writer_token_requires_authorization():
    """Unauthorized holders cannot get a WriterToken."""
    from runtime.authority import RuntimeAuthorityStore

    store = RuntimeAuthorityStore()
    try:
        store.issue_writer_token("random_module")
        raise AssertionError("Should not reach here")
    except PermissionError:
        pass


def test_writer_token_authorized():
    """Authorized holders get a valid WriterToken."""
    from runtime.authority import RuntimeAuthorityStore

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    assert token.holder == "governance_engine"


def test_write_increments_version():
    """Each write increments version monotonically."""
    from runtime.authority import RuntimeAuthorityStore

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    snap = token.write(1000, system_mode="SAFE")
    assert snap.version == 1
    assert snap.system_mode == "SAFE"
    snap2 = token.write(2000, health_score=0.8)
    assert snap2.version == 2
    assert snap2.health_score == 0.8


def test_write_invalid_field_raises():
    """Writing invalid fields raises ValueError."""
    from runtime.authority import RuntimeAuthorityStore

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    try:
        token.write(1000, nonexistent_field="bad")
        raise AssertionError("Should not reach here")
    except ValueError:
        pass


def test_subscription_fires_on_change():
    """Subscriptions fire when relevant slice changes."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.subscriptions import StateSlice, SubscriptionManager

    store = RuntimeAuthorityStore()
    mgr = SubscriptionManager(store)
    token = store.issue_writer_token("governance_engine")

    notifications: list[str] = []

    def on_mode_change(old, new):
        notifications.append(f"{old.system_mode}->{new.system_mode}")

    mgr.subscribe(subscriber="test", slice=StateSlice.SYSTEM_MODE, callback=on_mode_change)

    token.write(1000, system_mode="LIVE")
    assert notifications == ["PAPER->LIVE"]

    # Writing a non-mode field should NOT fire the mode subscription
    token.write(2000, health_score=0.5)
    assert len(notifications) == 1


def test_subscription_all_fires_on_any_change():
    """ALL subscription fires on any state change."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.subscriptions import StateSlice, SubscriptionManager

    store = RuntimeAuthorityStore()
    mgr = SubscriptionManager(store)
    token = store.issue_writer_token("governance_engine")

    count = []

    def on_any(old, new):
        count.append(1)

    mgr.subscribe(subscriber="test", slice=StateSlice.ALL, callback=on_any)
    token.write(1000, health_score=0.9)
    token.write(2000, system_mode="CANARY")
    assert len(count) == 2


def test_projection_market():
    """MarketProjection reflects store state."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.projections import ProjectionFactory

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("execution_fabric")
    factory = ProjectionFactory(store)

    token.write(5000, market_connected=True, last_market_ts_ns=5000)
    proj = factory.market()
    assert proj.connected is True
    assert proj.last_tick_ts_ns == 5000


def test_projection_execution():
    """ExecutionProjection reflects trading modes."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.projections import ProjectionFactory

    store = RuntimeAuthorityStore()
    factory = ProjectionFactory(store)

    proj = factory.execution()
    assert proj.live_execution_blocked is True
    assert "NORMAL" in proj.trading_modes


def test_projection_governance():
    """GovernanceProjection reflects system state."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.projections import ProjectionFactory

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("governance_engine")
    factory = ProjectionFactory(store)

    token.write(1000, freeze_active=True, system_mode="LOCKED")
    proj = factory.governance()
    assert proj.freeze_active is True
    assert proj.system_mode == "LOCKED"
    assert proj.operator_id == "ronald"


def test_authority_writer_set_learning():
    """AuthorityWriter.set_learning updates OperatorAuthority."""
    from core.contracts.operator_authority import LearningAuthority
    from runtime.authority import RuntimeAuthorityStore
    from runtime.writer import AuthorityWriter

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("operator_interface_bridge")
    writer = AuthorityWriter(token)

    current = store.snapshot.operator_authority
    snap = writer.set_learning(value=LearningAuthority.OFF, ts_ns=1000, current=current)
    assert snap.operator_authority.learning == LearningAuthority.OFF
    assert snap.learning_active is False


def test_authority_writer_set_live_execution():
    """AuthorityWriter.set_live_execution updates block state."""
    from core.contracts.operator_authority import LiveExecutionAuthority
    from runtime.authority import RuntimeAuthorityStore
    from runtime.writer import AuthorityWriter

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("operator_interface_bridge")
    writer = AuthorityWriter(token)

    current = store.snapshot.operator_authority
    snap = writer.set_live_execution(
        value=LiveExecutionAuthority.ARMED, ts_ns=2000, current=current
    )
    assert snap.live_execution_blocked is False
    assert snap.operator_authority.live_execution == LiveExecutionAuthority.ARMED


def test_authority_writer_hazard_management():
    """AuthorityWriter can add and clear hazards."""
    from runtime.authority import RuntimeAuthorityStore
    from runtime.writer import AuthorityWriter

    store = RuntimeAuthorityStore()
    token = store.issue_writer_token("system_engine")
    writer = AuthorityWriter(token)

    snap = writer.record_hazard(code="FEED_TIMEOUT", ts_ns=1000, current_hazards=())
    assert "FEED_TIMEOUT" in snap.active_hazards
    assert snap.health_score < 1.0

    snap2 = writer.clear_hazard(
        code="FEED_TIMEOUT", ts_ns=2000, current_hazards=snap.active_hazards
    )
    assert "FEED_TIMEOUT" not in snap2.active_hazards
    assert snap2.health_score == 1.0
