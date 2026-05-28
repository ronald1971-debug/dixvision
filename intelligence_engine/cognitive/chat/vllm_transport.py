# ADAPTED FROM: vllm-project/vllm
# (vllm/entrypoints/openai/api_server.py — FastAPI app exposing
#  /v1/chat/completions, /v1/completions, /v1/models;
#  vllm/engine/async_llm_engine.py — AsyncLLMEngine batch scheduler)
"""C-48 — vLLM high-throughput local inference transport.

This module connects to a locally running vLLM server via its
OpenAI-compatible REST endpoint. vLLM runs as a **separate process**
(``python -m vllm.entrypoints.openai.api_server --model ...``), never
imported into the RUNTIME tier.

What survives from upstream (vllm-project/vllm):
    * **OpenAI-compatible endpoint** —
      ``vllm/entrypoints/openai/api_server.py:158``: ``/v1/chat/completions``
      accepts ``model``, ``messages``, ``temperature``, ``max_tokens``,
      ``top_p``, ``stream``.  We POST the same JSON body.
    * **Batch scheduling** — the vLLM server internally uses continuous
      batching (``async_llm_engine.py``). This transport sends requests
      one-at-a-time; batching happens server-side transparently.
    * **Model listing** — ``/v1/models`` returns loaded model IDs.

What we replaced:
    * No ``vllm`` Python import — we only speak HTTP to the server.
    * ``httpx`` → stdlib ``urllib.request``.
    * Timestamps from caller (``ts_ns`` passthrough), never self-generated.

OFFLINE tier: vLLM inference is too heavy for RUNTIME hot path.
LiteLLM routes to the vLLM endpoint (see ``litellm_router.py``).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class VLLMResponse:
    """Parsed response from a vLLM /v1/chat/completions call."""

    content: str
    model: str = ""
    usage: Mapping[str, int] = field(default_factory=dict)
    error: str = ""


class VLLMTransport:
    """HTTP transport to a vLLM OpenAI-compatible server.

    Usage::

        transport = VLLMTransport(base_url="http://localhost:8000")
        resp = transport.chat(
            model="meta-llama/Llama-3-8B-Instruct",
            messages=[{"role": "user", "content": "hello"}],
        )
        print(resp.content)
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8000",
        api_key: str = "EMPTY",
        timeout_s: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        top_p: float = 1.0,
    ) -> VLLMResponse:
        """Send a chat completion request to the vLLM server."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": False,
        }
        try:
            resp = self._post("/v1/chat/completions", body)
            choices = resp.get("choices", [])
            content = choices[0]["message"]["content"] if choices else ""
            usage = resp.get("usage", {})
            return VLLMResponse(
                content=content,
                model=resp.get("model", model),
                usage=usage,
            )
        except Exception as e:
            return VLLMResponse(content="", error=f"{type(e).__name__}: {e}")

    def list_models(self) -> list[str]:
        """List models loaded on the vLLM server."""
        try:
            resp = self._get("/v1/models")
            data = resp.get("data", [])
            return [m.get("id", "") for m in data if isinstance(m, dict)]
        except Exception:
            return []

    def health(self) -> bool:
        """Check if the vLLM server is reachable."""
        try:
            self._get("/health")
            return True
        except Exception:
            return False

    # ---- internals -------------------------------------------------------

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self._api_key}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            return json.loads(resp.read())

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self._api_key}")
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            return json.loads(resp.read())


__all__ = ["VLLMResponse", "VLLMTransport"]
