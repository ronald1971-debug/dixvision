"""Tests for Tier C batch: C-48..C-55, C-64..C-66."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# C-48: vLLM transport
# ---------------------------------------------------------------------------


def test_vllm_transport_construction() -> None:
    from intelligence_engine.cognitive.chat.vllm_transport import VLLMTransport

    t = VLLMTransport(base_url="http://localhost:8000")
    assert t._base_url == "http://localhost:8000"


def test_vllm_transport_health_unreachable() -> None:
    from intelligence_engine.cognitive.chat.vllm_transport import VLLMTransport

    t = VLLMTransport(base_url="http://127.0.0.1:1")
    assert t.health() is False


def test_vllm_transport_chat_unreachable() -> None:
    from intelligence_engine.cognitive.chat.vllm_transport import VLLMTransport

    t = VLLMTransport(base_url="http://127.0.0.1:1", timeout_s=1)
    resp = t.chat(model="test", messages=[{"role": "user", "content": "hi"}])
    assert resp.content == ""
    assert resp.error != ""


# ---------------------------------------------------------------------------
# C-49: llama-cpp-python transport
# ---------------------------------------------------------------------------


def test_llama_transport_construction() -> None:
    from intelligence_engine.cognitive.chat.llama_transport import LlamaTransport

    t = LlamaTransport(model_path="/tmp/model.gguf", n_ctx=2048)
    assert t._model_path == "/tmp/model.gguf"
    assert t._n_ctx == 2048


def test_llama_transport_missing_dep() -> None:
    from intelligence_engine.cognitive.chat.llama_transport import LlamaTransport

    t = LlamaTransport(model_path="/nonexistent.gguf")
    resp = t.chat(messages=[{"role": "user", "content": "test"}])
    assert resp.error != ""


def test_llama_json_grammar_defined() -> None:
    from intelligence_engine.cognitive.chat.llama_transport import JSON_GRAMMAR

    assert "root" in JSON_GRAMMAR
    assert "object" in JSON_GRAMMAR


# ---------------------------------------------------------------------------
# C-50: TensorRT-LLM transport
# ---------------------------------------------------------------------------


def test_tensorrt_transport_construction() -> None:
    from intelligence_engine.cognitive.chat.tensorrt_transport import TensorRTTransport

    t = TensorRTTransport(base_url="http://localhost:8001")
    assert t._base_url == "http://localhost:8001"


def test_tensorrt_transport_health_unreachable() -> None:
    from intelligence_engine.cognitive.chat.tensorrt_transport import TensorRTTransport

    t = TensorRTTransport(base_url="http://127.0.0.1:1")
    assert t.health() is False


def test_tensorrt_transport_chat_unreachable() -> None:
    from intelligence_engine.cognitive.chat.tensorrt_transport import TensorRTTransport

    t = TensorRTTransport(base_url="http://127.0.0.1:1", timeout_s=1)
    resp = t.chat(model="test", messages=[{"role": "user", "content": "hi"}])
    assert resp.content == ""
    assert resp.error != ""


# ---------------------------------------------------------------------------
# C-51: QuestDB hot store
# ---------------------------------------------------------------------------


def test_questdb_write_and_count() -> None:
    from state.ledger.questdb_store import QuestDBHotStore

    store = QuestDBHotStore(in_memory=True)
    store.write_row("ticks", symbols={"symbol": "AAPL"}, columns={"price": 150.0})
    store.write_row("ticks", symbols={"symbol": "GOOG"}, columns={"price": 2800.0})
    assert store.row_count() == 2
    assert store.row_count("ticks") == 2


def test_questdb_flush() -> None:
    from state.ledger.questdb_store import QuestDBHotStore

    store = QuestDBHotStore(in_memory=True)
    store.write_row("trades", columns={"qty": 100})
    assert store.flush() == 1


def test_questdb_query_buffer() -> None:
    from state.ledger.questdb_store import QuestDBHotStore

    store = QuestDBHotStore(in_memory=True)
    store.write_row("ticks", symbols={"sym": "X"}, columns={"px": 10.5}, timestamp_ns=999)
    results = store.query("SELECT * FROM ticks")
    assert len(results) == 1
    assert results[0]["sym"] == "X"
    assert results[0]["px"] == 10.5


def test_questdb_ilp_line() -> None:
    from state.ledger.questdb_store import ILPRow, to_ilp_line

    row = ILPRow(table="trades", symbols={"venue": "NYSE"}, columns={"qty": 50}, timestamp_ns=123)
    line = to_ilp_line(row)
    assert line.startswith("trades,venue=NYSE")
    assert "qty=50i" in line
    assert line.endswith("123")


# ---------------------------------------------------------------------------
# C-52: InfluxDB store
# ---------------------------------------------------------------------------


def test_influxdb_write_and_count() -> None:
    from state.timeseries.influxdb_store import InfluxDBStore

    store = InfluxDBStore(in_memory=True)
    store.write_point("cpu", tags={"host": "dix-1"}, fields={"usage": 45.2})
    store.write_point("cpu", tags={"host": "dix-2"}, fields={"usage": 78.1})
    assert store.point_count() == 2
    assert store.point_count("cpu") == 2


def test_influxdb_query_buffer() -> None:
    from state.timeseries.influxdb_store import InfluxDBStore

    store = InfluxDBStore(in_memory=True)
    store.write_point("latency", tags={"path": "/api"}, fields={"ms": 12.5})
    results = store.query('from(bucket:"metrics")')
    assert len(results) == 1
    assert results[0]["path"] == "/api"


# ---------------------------------------------------------------------------
# C-53: LMDB store
# ---------------------------------------------------------------------------


def test_lmdb_put_get() -> None:
    from state.ledger.lmdb_store import LMDBStore

    store = LMDBStore(in_memory=True)
    assert store.put(b"key1", b"value1") is True
    assert store.get(b"key1") == b"value1"
    assert store.get(b"nonexistent") is None


def test_lmdb_delete() -> None:
    from state.ledger.lmdb_store import LMDBStore

    store = LMDBStore(in_memory=True)
    store.put(b"k", b"v")
    assert store.delete(b"k") is True
    assert store.delete(b"k") is False
    assert store.get(b"k") is None


def test_lmdb_exists_and_count() -> None:
    from state.ledger.lmdb_store import LMDBStore

    store = LMDBStore(in_memory=True)
    store.put(b"a", b"1")
    store.put(b"b", b"2")
    assert store.exists(b"a") is True
    assert store.exists(b"c") is False
    assert store.count() == 2


def test_lmdb_keys() -> None:
    from state.ledger.lmdb_store import LMDBStore

    store = LMDBStore(in_memory=True)
    store.put(b"x", b"1")
    store.put(b"y", b"2")
    assert set(store.keys()) == {b"x", b"y"}


# ---------------------------------------------------------------------------
# C-54: DeltaLake feature store
# ---------------------------------------------------------------------------


def test_delta_write_and_version() -> None:
    from state.feature_store_delta import DeltaFeatureStore, FeatureRow

    store = DeltaFeatureStore(in_memory=True)
    assert store.version() == 0
    rows = [
        FeatureRow(entity_key="AAPL", features={"momentum": 0.8}),
        FeatureRow(entity_key="GOOG", features={"momentum": 0.6}),
    ]
    store.write_features(rows)
    assert store.version() == 1
    assert store.row_count() == 2


def test_delta_get_online_features() -> None:
    from state.feature_store_delta import DeltaFeatureStore, FeatureRow

    store = DeltaFeatureStore(in_memory=True)
    store.write_features(
        [
            FeatureRow(entity_key="AAPL", features={"vol": 0.3, "mom": 0.8}),
            FeatureRow(entity_key="TSLA", features={"vol": 0.9, "mom": 0.2}),
        ]
    )
    results = store.get_online_features(["AAPL", "TSLA"], ["vol"])
    assert len(results) == 2
    assert results[0]["vol"] == 0.3
    assert results[1]["vol"] == 0.9


def test_delta_time_travel() -> None:
    from state.feature_store_delta import DeltaFeatureStore, FeatureRow

    store = DeltaFeatureStore(in_memory=True)
    store.write_features([FeatureRow(entity_key="A", features={"x": 1.0})])
    store.write_features([FeatureRow(entity_key="B", features={"x": 2.0})])
    # Version 1 has only A; version 2 has A+B
    v1 = store.load_as_version(1)
    assert len(v1) == 1
    v2 = store.load_as_version(2)
    assert len(v2) == 2


# ---------------------------------------------------------------------------
# C-55: LakeFS feature store
# ---------------------------------------------------------------------------


def test_lakefs_branch_and_commit() -> None:
    from state.feature_store_lakefs import LakeFSFeatureStore

    store = LakeFSFeatureStore(in_memory=True)
    assert store.create_branch("experiment-1") is True
    assert store.create_branch("experiment-1") is False  # already exists
    store.upload("experiment-1", "features/train.parquet", b"data123")
    commit = store.commit("experiment-1", "add training features")
    assert commit is not None
    assert commit.branch == "experiment-1"


def test_lakefs_diff() -> None:
    from state.feature_store_lakefs import LakeFSFeatureStore

    store = LakeFSFeatureStore(in_memory=True)
    store.create_branch("dev")
    store.upload("dev", "new_file.csv", b"content")
    diffs = store.diff("dev", "main")
    assert len(diffs) == 1
    assert diffs[0].change_type == "added"


def test_lakefs_merge() -> None:
    from state.feature_store_lakefs import LakeFSFeatureStore

    store = LakeFSFeatureStore(in_memory=True)
    store.create_branch("feature")
    store.upload("feature", "data.parquet", b"payload")
    assert store.merge("feature", "main") is True
    assert store.read_object("main", "data.parquet") == b"payload"


# ---------------------------------------------------------------------------
# C-64: Temporal governance workflow
# ---------------------------------------------------------------------------


def test_approval_workflow_approve() -> None:
    from governance_engine.workflows.approval_workflow import (
        ApprovalRequest,
        ApprovalStatus,
        GovernanceApprovalWorkflow,
    )

    wf = GovernanceApprovalWorkflow()
    req = ApprovalRequest(
        proposal_id="p-001",
        proposal_type="mode_shift",
        requester="operator",
        payload={"target_mode": "LIVE"},
    )
    result = wf.run(req)
    assert result.status == ApprovalStatus.APPROVED


def test_approval_workflow_reject_invalid() -> None:
    from governance_engine.workflows.approval_workflow import (
        ApprovalRequest,
        ApprovalStatus,
        GovernanceApprovalWorkflow,
    )

    wf = GovernanceApprovalWorkflow()
    req = ApprovalRequest(
        proposal_id="p-002",
        proposal_type="invalid_type",
        requester="operator",
    )
    result = wf.run(req)
    assert result.status == ApprovalStatus.REJECTED


def test_approval_workflow_signal() -> None:
    from governance_engine.workflows.approval_workflow import (
        ApprovalStatus,
        GovernanceApprovalWorkflow,
    )

    wf = GovernanceApprovalWorkflow()
    wf.signal_reject("p-003", "admin", reason="risk too high")
    assert wf.get_status("p-003") == ApprovalStatus.FAILED  # not in pending


# ---------------------------------------------------------------------------
# C-65: Dagster pipeline orchestrator
# ---------------------------------------------------------------------------


def test_pipeline_single_asset() -> None:
    from evolution_engine.pipeline_orchestrator import AssetStatus, PipelineOrchestrator

    orch = PipelineOrchestrator()

    @orch.asset(name="data")
    def get_data() -> list[int]:
        return [1, 2, 3]

    result = orch.execute("test_job")
    assert result.success is True
    assert len(result.assets) == 1
    assert result.assets[0].status == AssetStatus.SUCCESS
    assert result.assets[0].output == [1, 2, 3]


def test_pipeline_chain() -> None:
    from evolution_engine.pipeline_orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()

    @orch.asset(name="raw")
    def raw() -> dict[str, list[int]]:
        return {"values": [1, 2, 3]}

    @orch.asset(name="transformed", deps=["raw"])
    def transformed(raw: dict[str, list[int]]) -> list[int]:
        return [x * 2 for x in raw["values"]]

    result = orch.execute("pipeline")
    assert result.success is True
    assert len(result.assets) == 2
    assert result.assets[1].output == [2, 4, 6]


def test_pipeline_failure() -> None:
    from evolution_engine.pipeline_orchestrator import AssetStatus, PipelineOrchestrator

    orch = PipelineOrchestrator()

    @orch.asset(name="broken")
    def broken() -> None:
        raise RuntimeError("oops")

    result = orch.execute()
    assert result.success is False
    assert result.assets[0].status == AssetStatus.FAILED


# ---------------------------------------------------------------------------
# C-66: Celery task queue
# ---------------------------------------------------------------------------


def test_task_queue_single() -> None:
    from evolution_engine.task_queue import TaskQueue, TaskStatus

    tq = TaskQueue(in_memory=True)

    @tq.task(name="add")
    def add(a: int = 0, b: int = 0) -> int:
        return a + b

    result = tq.apply("add", 2, 3)
    assert result.status == TaskStatus.SUCCESS
    assert result.result == 5


def test_task_queue_chain() -> None:
    from evolution_engine.task_queue import TaskQueue

    tq = TaskQueue(in_memory=True)

    @tq.task(name="double")
    def double(x: int) -> int:
        return x * 2

    @tq.task(name="add_one")
    def add_one(x: int) -> int:
        return x + 1

    results = tq.chain(["double", "add_one"], initial_input=5)
    assert len(results) == 2
    assert results[0].result == 10
    assert results[1].result == 11


def test_task_queue_retry() -> None:
    from evolution_engine.task_queue import TaskQueue, TaskStatus

    tq = TaskQueue(in_memory=True)
    counter = {"n": 0}

    @tq.task(name="flaky", max_retries=2)
    def flaky() -> str:
        counter["n"] += 1
        if counter["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = tq.apply("flaky")
    assert result.status == TaskStatus.SUCCESS
    assert result.retries == 2


def test_task_queue_not_registered() -> None:
    from evolution_engine.task_queue import TaskQueue, TaskStatus

    tq = TaskQueue(in_memory=True)
    result = tq.apply("nonexistent")
    assert result.status == TaskStatus.FAILED
    assert "not registered" in result.error
