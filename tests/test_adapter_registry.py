"""D1 — adapter registry unit tests."""

from __future__ import annotations

import pytest

from execution_engine.adapters import (
    AdapterRegistry,
    AdapterState,
    HummingbotAdapter,
    PumpFunAdapter,
    UniswapXAdapter,
    default_registry,
)


def test_default_registry_has_three_disconnected():
    reg = default_registry()
    snap = reg.snapshot()
    names = {s.name for s in snap}
    assert "hummingbot:paper" in names
    assert "pumpfun" in names
    if UniswapXAdapter is not None:
        assert len(reg) >= 3
        assert any(n.startswith("uniswapx:") for n in names)
    else:
        assert len(reg) >= 2
    # Stage-9 paper venue adapters (binance_paper, coinbase_paper, etc.) are
    # credential-free and intentionally start READY. Credential-backed adapters
    # (hummingbot, binance, alpaca, ibkr, pumpfun, uniswapx) must be DISCONNECTED.
    paper_names = {"binance_paper", "coinbase_paper", "kraken_paper",
                   "alpaca_paper", "oanda_paper", "ibkr_paper"}
    for s in snap:
        if s.name in paper_names:
            assert s.state is AdapterState.READY, f"{s.name} should be READY"
        else:
            assert s.state is AdapterState.DISCONNECTED, f"{s.name} should be DISCONNECTED"


def test_default_registry_is_singleton():
    a = default_registry()
    b = default_registry()
    assert a is b


def test_registry_rejects_duplicate_names():
    reg = AdapterRegistry()
    reg.add(HummingbotAdapter(connector="x"))
    with pytest.raises(ValueError):
        reg.add(HummingbotAdapter(connector="x"))


def test_registry_get_by_name():
    reg = AdapterRegistry()
    a = PumpFunAdapter()
    reg.add(a)
    assert reg.get("pumpfun") is a
    assert reg.get("missing") is None


@pytest.mark.skipif(UniswapXAdapter is None, reason="eth_account not installed")
def test_uniswapx_chain_id_in_name():
    a = UniswapXAdapter(chain_id=8453)
    assert "8453" in a.name


def test_pumpfun_priority_fee_validation():
    with pytest.raises(ValueError):
        PumpFunAdapter(priority_fee_micro_lamports=-1)


@pytest.mark.skipif(UniswapXAdapter is None, reason="eth_account not installed")
def test_uniswapx_chain_id_validation():
    with pytest.raises(ValueError):
        UniswapXAdapter(chain_id=0)
