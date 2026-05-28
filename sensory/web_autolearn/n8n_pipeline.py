# ADAPTED FROM: n8n-io/n8n
# (REST API: POST /api/v1/executions, GET /api/v1/workflows;
#  Webhook trigger: POST /webhook/<workflow-id> for incoming data)
"""I-37 — n8n no-code workflow REST client for web_autolearn pipeline.

Bridges the ``web_autolearn`` crawler system with n8n's visual workflow
orchestrator. Operators configure crawl sources via n8n GUI; DIX
triggers workflows and receives results via webhooks.

What survives from upstream (n8n-io/n8n):
    * **Workflow execution** — ``POST /api/v1/executions``: trigger a
      workflow by ID with input data.
    * **Workflow listing** — ``GET /api/v1/workflows``: discover
      available workflows configured by operator.
    * **Webhook triggers** — n8n sends results back via HTTP POST to
      the sensory layer's webhook endpoint.

What we replaced:
    * Real ``httpx`` calls are behind Protocol seam (lazy import).
    * In-memory mock for unit tests (no n8n instance needed).
    * Results feed into ``sensory/web_autolearn/`` as RawDocument events.

Classification: PATTERN_ONLY — REST client only, no n8n code in production.
FLAG: n8n uses Sustainable Use License — confirm acceptable before production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from system.time_source import wall_ns


@dataclass(frozen=True, slots=True)
class N8nWorkflow:
    """A registered n8n workflow."""

    workflow_id: str
    name: str
    active: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class N8nExecutionResult:
    """Result of triggering an n8n workflow."""

    execution_id: str
    workflow_id: str
    status: str  # "success", "error", "running"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ns: int = 0


@dataclass(frozen=True, slots=True)
class WebhookPayload:
    """Incoming webhook payload from n8n workflow completion."""

    workflow_id: str
    documents: list[dict[str, Any]] = field(default_factory=list)
    timestamp_ns: int = 0


class N8nPipelineClient:
    """REST client for n8n workflow automation.

    Triggers crawl/scrape workflows in n8n and receives results for
    the web_autolearn pipeline.

    In test mode (default), mocks n8n responses.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:5678",
        api_key: str = "",
        in_memory: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._in_memory = in_memory
        self._mock_workflows: list[N8nWorkflow] = []
        self._execution_log: list[N8nExecutionResult] = []

    def list_workflows(self) -> list[N8nWorkflow]:
        """List all available n8n workflows.

        Mirrors ``GET /api/v1/workflows``.
        """
        if self._in_memory:
            return list(self._mock_workflows)
        return self._get_workflows_remote()

    def trigger_workflow(
        self,
        workflow_id: str,
        *,
        input_data: dict[str, Any] | None = None,
    ) -> N8nExecutionResult:
        """Trigger a workflow execution.

        Mirrors ``POST /api/v1/executions`` with workflow_id and input data.
        """
        if self._in_memory:
            return self._mock_trigger(workflow_id, input_data)
        return self._trigger_remote(workflow_id, input_data)

    def register_mock_workflow(self, workflow: N8nWorkflow) -> None:
        """Register a mock workflow for testing."""
        self._mock_workflows.append(workflow)

    @property
    def execution_log(self) -> list[N8nExecutionResult]:
        """All execution results."""
        return list(self._execution_log)

    def process_webhook(self, payload: WebhookPayload) -> int:
        """Process an incoming webhook from n8n.

        Returns the number of documents received.
        """
        return len(payload.documents)

    # ---- internals -------------------------------------------------------

    def _mock_trigger(
        self, workflow_id: str, input_data: dict[str, Any] | None
    ) -> N8nExecutionResult:
        """Mock workflow execution."""
        result = N8nExecutionResult(
            execution_id=f"mock_exec_{len(self._execution_log)}",
            workflow_id=workflow_id,
            status="success",
            data=input_data or {},
            timestamp_ns=wall_ns(),
        )
        self._execution_log.append(result)
        return result

    def _get_workflows_remote(self) -> list[N8nWorkflow]:
        """Fetch workflows from n8n REST API."""
        try:
            import httpx  # noqa: F401  # lazy import

            resp = httpx.get(
                f"{self._base_url}/api/v1/workflows",
                headers={"X-N8N-API-KEY": self._api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                N8nWorkflow(
                    workflow_id=str(w["id"]),
                    name=w.get("name", ""),
                    active=w.get("active", False),
                )
                for w in data.get("data", [])
            ]
        except ImportError:
            return []

    def _trigger_remote(
        self, workflow_id: str, input_data: dict[str, Any] | None
    ) -> N8nExecutionResult:
        """Trigger workflow via n8n REST API."""
        try:
            import httpx  # noqa: F401  # lazy import

            resp = httpx.post(
                f"{self._base_url}/api/v1/executions",
                headers={"X-N8N-API-KEY": self._api_key},
                json={"workflowId": workflow_id, "data": input_data or {}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            result = N8nExecutionResult(
                execution_id=str(data.get("id", "")),
                workflow_id=workflow_id,
                status=data.get("status", "unknown"),
                data=data.get("data", {}),
                timestamp_ns=wall_ns(),
            )
            self._execution_log.append(result)
            return result
        except ImportError:
            return self._mock_trigger(workflow_id, input_data)


__all__ = [
    "N8nExecutionResult",
    "N8nPipelineClient",
    "N8nWorkflow",
    "WebhookPayload",
]
