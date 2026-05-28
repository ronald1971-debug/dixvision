"""Tests for Tier C batch 2: C-01, C-56..C-63, C-69..C-71."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# C-01: Bytewax event fabric (already implemented — smoke test)
# ---------------------------------------------------------------------------


def test_event_fabric_dataflow_map() -> None:
    from system_engine.streaming.event_fabric import Dataflow, run_dataflow

    df = Dataflow(name="test").map(lambda x: x * 2)
    results = run_dataflow(df, [1, 2, 3])
    assert len(results) == 3
    assert results[0].payload == 2
    assert results[2].payload == 6


def test_event_fabric_dataflow_filter() -> None:
    from system_engine.streaming.event_fabric import Dataflow, run_dataflow

    df = Dataflow(name="pos").filter(lambda x: x > 0)
    results = run_dataflow(df, [1, -2, 3, -4])
    assert len(results) == 2
    assert results[0].payload == 1
    assert results[1].payload == 3


# ---------------------------------------------------------------------------
# C-56: PostgreSQL ledger store
# ---------------------------------------------------------------------------


def test_postgres_store_append_and_read() -> None:
    from state.ledger.postgres_store import LedgerRow, PostgresLedgerStore

    store = PostgresLedgerStore(in_memory=True)
    r1 = LedgerRow(seq=0, ts_ns=100, kind="signal", payload="{}", hash_chain="aaa")
    r2 = LedgerRow(seq=1, ts_ns=200, kind="exec", payload="{}", hash_chain="bbb")
    store.append(r1)
    store.append(r2)
    assert store.count() == 2
    assert store.latest_seq() == 1


def test_postgres_store_read_from() -> None:
    from state.ledger.postgres_store import LedgerRow, PostgresLedgerStore

    store = PostgresLedgerStore(in_memory=True)
    for i in range(5):
        store.append(LedgerRow(seq=i, ts_ns=i * 100, kind="x", payload="", hash_chain=f"h{i}"))
    rows = store.read_from(seq=3)
    assert len(rows) == 2
    assert rows[0].seq == 3


def test_postgres_store_verify_chain() -> None:
    from state.ledger.postgres_store import LedgerRow, PostgresLedgerStore

    store = PostgresLedgerStore(in_memory=True)
    for i in range(10):
        store.append(LedgerRow(seq=i, ts_ns=i, kind="t", payload="", hash_chain=""))
    assert store.verify_chain() is True


# ---------------------------------------------------------------------------
# C-57: ClickHouse analytics store
# ---------------------------------------------------------------------------


def test_clickhouse_insert_and_count() -> None:
    from state.analytics.clickhouse_store import ClickHouseStore

    store = ClickHouseStore(in_memory=True)
    store.insert(
        "trades", [("AAPL", 150.0, 100), ("GOOG", 2800.0, 50)], columns=["sym", "px", "qty"]
    )
    assert store.table_row_count("trades") == 2


def test_clickhouse_query() -> None:
    from state.analytics.clickhouse_store import ClickHouseStore

    store = ClickHouseStore(in_memory=True)
    store.insert("pnl", [(1.5,), (2.3,)], columns=["return_pct"])
    result = store.query("SELECT * FROM pnl")
    assert result.row_count == 2
    assert len(result.column_names) == 1


# ---------------------------------------------------------------------------
# C-59: Zipline backtester
# ---------------------------------------------------------------------------


def test_zipline_backtester_basic() -> None:
    from simulation.backtester_zipline import BacktestBar, ZiplineBacktester, ZiplineContext

    bt = ZiplineBacktester(capital=10_000)
    bt.set_initialize(lambda ctx: None)

    def strategy(ctx: ZiplineContext, bar: BacktestBar) -> None:
        if bar.close < 100 and "AAPL" not in ctx.positions:
            ctx.positions["AAPL"] = 10.0
            ctx.cash -= 10.0 * bar.close
            ctx.orders.append({"symbol": "AAPL", "qty": 10, "side": "buy"})

    bt.set_handle_data(strategy)

    bars = [
        BacktestBar(
            symbol="AAPL",
            timestamp_ns=i * 1_000_000,
            open=95.0 + i,
            high=100.0 + i,
            low=90.0 + i,
            close=95.0 + i,
        )
        for i in range(10)
    ]
    result = bt.run(bars)
    assert result.final_value > 0
    assert result.num_trades > 0


# ---------------------------------------------------------------------------
# C-60: Risk parity optimizer
# ---------------------------------------------------------------------------


def test_risk_parity_hrp() -> None:
    from intelligence_engine.portfolio.risk_parity import RiskParityOptimizer

    opt = RiskParityOptimizer()
    returns = {
        "AAPL": [0.01, -0.02, 0.03, 0.01, -0.01],
        "GOOG": [0.02, -0.01, 0.01, 0.02, -0.02],
        "TSLA": [0.05, -0.05, 0.04, -0.03, 0.02],
    }
    result = opt.hrp(returns)
    assert len(result.weights) == 3
    assert abs(sum(result.weights.values()) - 1.0) < 1e-10


def test_risk_parity_min_vol() -> None:
    from intelligence_engine.portfolio.risk_parity import RiskParityOptimizer

    opt = RiskParityOptimizer()
    returns = {"A": [0.01, 0.02, 0.01], "B": [0.1, -0.1, 0.1]}
    result = opt.min_volatility(returns)
    # A has lower variance, should get higher weight
    assert result.weights["A"] > result.weights["B"]


def test_risk_parity_equal_weight() -> None:
    from intelligence_engine.portfolio.risk_parity import RiskParityOptimizer

    opt = RiskParityOptimizer()
    result = opt.equal_weight(["A", "B", "C", "D"])
    assert all(abs(w - 0.25) < 1e-10 for w in result.weights.values())


# ---------------------------------------------------------------------------
# C-61: Regime forecaster
# ---------------------------------------------------------------------------


def test_forecaster_linear() -> None:
    from intelligence_engine.macro.forecaster import RegimeForecaster

    fc = RegimeForecaster(method="linear")
    result = fc.forecast([100, 101, 102, 103, 104], horizon=3)
    assert result.horizon == 3
    assert len(result.probabilities) == 3
    assert result.trend > 0  # upward trend


def test_forecaster_exponential() -> None:
    from intelligence_engine.macro.forecaster import RegimeForecaster

    fc = RegimeForecaster(method="exponential")
    result = fc.forecast([50, 48, 46, 44, 42], horizon=5)
    assert result.trend < 0  # downward trend


# ---------------------------------------------------------------------------
# C-63: W&B tracker
# ---------------------------------------------------------------------------


def test_wandb_tracker_lifecycle() -> None:
    from evolution_engine.wandb_tracker import WandbTracker

    tracker = WandbTracker(project="test")
    run = tracker.init(config={"lr": 0.001}, tags=["baseline"])
    assert run.project == "test"
    assert tracker.log(run.run_id, {"loss": 0.5}) is True
    assert tracker.log(run.run_id, {"loss": 0.3}) is True
    assert tracker.finish(run.run_id) is True
    assert tracker.log(run.run_id, {"loss": 0.1}) is False  # finished


def test_wandb_tracker_artifacts() -> None:
    from evolution_engine.wandb_tracker import WandbTracker

    tracker = WandbTracker()
    run = tracker.init()
    tracker.log_artifact(run.run_id, "model.pt")
    assert "model.pt" in run.artifacts


# ---------------------------------------------------------------------------
# C-67: Dask distributed analytics
# ---------------------------------------------------------------------------


def test_dask_delayed_compute() -> None:
    from evolution_engine.distributed_analytics import DistributedAnalytics

    da = DistributedAnalytics()

    @da.delayed("load")
    def load() -> list[int]:
        return [1, 2, 3, 4, 5]

    @da.delayed("stats")
    def stats(data: list[int]) -> dict[str, float]:
        return {"mean": sum(data) / len(data)}

    data_node = load()
    stats_node = stats(data_node)
    result = da.compute(stats_node)
    assert result == {"mean": 3.0}


# ---------------------------------------------------------------------------
# C-68: Kubeflow pipeline
# ---------------------------------------------------------------------------


def test_kubeflow_pipeline_compile() -> None:
    from evolution_engine.kubeflow_pipeline import KubeflowPipeline

    kf = KubeflowPipeline("train_pipeline")

    @kf.component(name="preprocess", outputs=["features"])
    def preprocess() -> dict[str, str]:
        return {"features": "processed"}

    @kf.component(name="train", inputs=["features"], outputs=["model"])
    def train(features: str = "") -> dict[str, str]:
        return {"model": "trained"}

    kf.connect("preprocess", "train")
    spec = kf.compile()
    assert spec.name == "train_pipeline"
    assert len(spec.components) == 2
    d = spec.to_dict()
    assert d["pipelineInfo"]["name"] == "train_pipeline"


# ---------------------------------------------------------------------------
# C-69: Credential crypto
# ---------------------------------------------------------------------------


def test_crypto_encrypt_decrypt() -> None:
    from system_engine.credentials.crypto import CredentialCrypto

    crypto = CredentialCrypto(iterations=1000)  # low for test speed
    blob = crypto.encrypt(b"secret-api-key", passphrase="mypassword")
    plaintext = crypto.decrypt(blob, passphrase="mypassword")
    assert plaintext == b"secret-api-key"


def test_crypto_wrong_passphrase() -> None:
    from system_engine.credentials.crypto import CredentialCrypto

    crypto = CredentialCrypto(iterations=1000)
    blob = crypto.encrypt(b"data", passphrase="correct")
    result = crypto.decrypt(blob, passphrase="wrong")
    # XOR fallback won't match — result will differ
    assert result != b"data"


def test_crypto_hash_id() -> None:
    from system_engine.credentials.crypto import CredentialCrypto

    crypto = CredentialCrypto()
    h = crypto.hash_credential_id("binance_api_key")
    assert len(h) == 16  # truncated SHA-256


# ---------------------------------------------------------------------------
# C-70: Vault backend
# ---------------------------------------------------------------------------


def test_vault_write_read() -> None:
    from system_engine.credentials.vault_backend import VaultBackend

    vault = VaultBackend(in_memory=True)
    assert vault.write_secret("dix/keys", {"api": "k123"}) is True
    secret = vault.read_secret("dix/keys")
    assert secret is not None
    assert secret.data["api"] == "k123"


def test_vault_versioning() -> None:
    from system_engine.credentials.vault_backend import VaultBackend

    vault = VaultBackend(in_memory=True)
    vault.write_secret("path/x", {"v": "1"})
    vault.write_secret("path/x", {"v": "2"})
    secret = vault.read_secret("path/x")
    assert secret is not None
    assert secret.version == 2
    assert secret.data["v"] == "2"


def test_vault_delete() -> None:
    from system_engine.credentials.vault_backend import VaultBackend

    vault = VaultBackend(in_memory=True)
    vault.write_secret("temp", {"k": "v"})
    assert vault.delete_secret("temp") is True
    assert vault.read_secret("temp") is None


# ---------------------------------------------------------------------------
# C-71: Patch signer
# ---------------------------------------------------------------------------


def test_patch_signer_sign_verify() -> None:
    from governance_engine.control_plane.patch_signer import PatchSigner

    signer = PatchSigner(identity="test@dix.io")
    artifact = b"strategy-weights-v2.bin"
    result = signer.sign(artifact)
    assert result.signer_identity == "test@dix.io"
    assert signer.verify(artifact, result) is True


def test_patch_signer_tampered() -> None:
    from governance_engine.control_plane.patch_signer import PatchSigner

    signer = PatchSigner()
    result = signer.sign(b"original")
    assert signer.verify(b"tampered", result) is False
