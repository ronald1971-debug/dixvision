"""Tests for Tier 3 memecoin execution layer."""

from execution_engine.memecoin.dex_router import (
    Chain,
    DEXProtocol,
    DEXRouter,
)
from execution_engine.memecoin.meme_risk_policy import (
    MemePositionLimits,
    MemeRejectionReason,
    MemeRiskPolicy,
)
from execution_engine.memecoin.paper_broker_meme import (
    MemeOrderStatus,
    PaperBrokerMeme,
)
from execution_engine.memecoin.sniper import (
    MemeSniper,
    SnipePhase,
)


def test_risk_policy_all_passed():
    policy = MemeRiskPolicy()
    report = policy.evaluate(
        token_address="0xabc",
        chain="solana",
        proposed_size_sol=0.1,
        mint_authority_revoked=True,
        freeze_authority_revoked=True,
        update_authority_revoked=True,
        bundle_detected=False,
        dev_wallet_clean=True,
        lp_locked=True,
        honeypot_simulation_passed=True,
        smart_money_holders=5,
        smart_money_net_buy=10.0,
        sensors_online=True,
        ts_ns=1000,
    )
    assert report.passed is True
    assert report.rejection_reason is None


def test_risk_policy_honeypot_rejected():
    policy = MemeRiskPolicy()
    report = policy.evaluate(
        token_address="0xhoney",
        proposed_size_sol=0.1,
        mint_authority_revoked=True,
        freeze_authority_revoked=True,
        update_authority_revoked=True,
        bundle_detected=False,
        dev_wallet_clean=True,
        lp_locked=True,
        honeypot_simulation_passed=False,
        sensors_online=True,
        ts_ns=1000,
    )
    assert report.passed is False
    assert report.rejection_reason == MemeRejectionReason.HONEYPOT_DETECTED


def test_risk_policy_sensor_offline():
    policy = MemeRiskPolicy()
    report = policy.evaluate(
        token_address="0x123",
        proposed_size_sol=0.1,
        sensors_online=False,
        ts_ns=1000,
    )
    assert report.passed is False
    assert report.rejection_reason == MemeRejectionReason.SENSOR_OFFLINE


def test_risk_policy_position_cap():
    limits = MemePositionLimits(max_per_trade_sol=0.5)
    policy = MemeRiskPolicy(limits=limits)
    report = policy.evaluate(
        token_address="0xabc",
        proposed_size_sol=1.0,
        mint_authority_revoked=True,
        freeze_authority_revoked=True,
        update_authority_revoked=True,
        bundle_detected=False,
        dev_wallet_clean=True,
        lp_locked=True,
        honeypot_simulation_passed=True,
        sensors_online=True,
        ts_ns=1000,
    )
    assert report.passed is False
    assert report.rejection_reason == MemeRejectionReason.POSITION_CAP_EXCEEDED


def test_paper_broker_meme_buy():
    broker = PaperBrokerMeme(initial_bankroll_sol=10.0)
    fill = broker.submit_buy(
        token_address="0xtoken1",
        size_sol=0.5,
        pool_liquidity_sol=100.0,
        token_age_seconds=300,
        ts_ns=1000,
    )
    assert fill.status in (
        MemeOrderStatus.FILLED,
        MemeOrderStatus.PARTIAL,
        MemeOrderStatus.FRONTRUN,
        MemeOrderStatus.REVERTED,
    )
    assert broker.bankroll < 10.0  # spent something


def test_paper_broker_meme_insufficient_bankroll():
    broker = PaperBrokerMeme(initial_bankroll_sol=0.001)
    fill = broker.submit_buy(
        token_address="0xtoken2",
        size_sol=5.0,
        ts_ns=2000,
    )
    assert fill.status == MemeOrderStatus.REJECTED


def test_dex_router_quote():
    router = DEXRouter()
    quote = router.get_best_quote(
        chain=Chain.SOLANA,
        input_token="SOL",
        output_token="MEME",
        amount=1.0,
        ts_ns=1000,
    )
    assert quote is not None
    assert quote.dex == DEXProtocol.JUPITER
    assert quote.output_amount > 0
    assert quote.output_amount < 1.0  # slippage


def test_sniper_two_phase():
    sniper = MemeSniper(enabled=True, confirmation_delay_ns=1000)
    attempt = sniper.create_attempt(
        token_address="0xnewtoken",
        size_sol=0.1,
        ts_ns=100,
    )
    assert attempt is not None
    assert attempt.phase == SnipePhase.PENDING

    # Phase 1
    assert sniper.start_phase1(attempt.snipe_id, safety_passed=True, ts_ns=200)
    assert attempt.phase == SnipePhase.PHASE1_EXECUTING

    sniper.complete_phase1(attempt.snipe_id, filled=True, price=0.001)
    assert attempt.phase == SnipePhase.PHASE2_WAITING

    # Phase 2 — too early
    assert not sniper.can_start_phase2(attempt.snipe_id, ts_ns=500)

    # Phase 2 — after delay
    assert sniper.can_start_phase2(attempt.snipe_id, ts_ns=1500)
    assert sniper.start_phase2(
        attempt.snipe_id,
        confirmation_passed=True,
        ts_ns=1500,
    )
    sniper.complete_phase2(attempt.snipe_id, filled=True, price=0.0015)
    assert attempt.phase == SnipePhase.COMPLETE


def test_sniper_disabled():
    sniper = MemeSniper(enabled=False)
    attempt = sniper.create_attempt(token_address="0x123", ts_ns=100)
    assert attempt is None
