# ADAPTED FROM: NVIDIA/TensorRT-LLM
# (tensorrt_llm/runtime/generation.py — GenerationSession, generate();
#  examples/server/openai_api_server.py — OpenAI-compatible REST endpoint;
#  tensorrt_llm/hlapi/llm.py — LLM high-level class, generate() method)
"""C-50 — TensorRT-LLM GPU-accelerated production inference transport.

This module connects to a TensorRT-LLM server exposing an
OpenAI-compatible REST endpoint. TensorRT-LLM runs as a **separate
process** (typically via Triton Inference Server or the built-in
``trtllm-serve`` launcher), never imported into the RUNTIME tier.

What survives from upstream (NVIDIA/TensorRT-LLM):
    * **OpenAI-compatible endpoint** — ``examples/server/openai_api_server.py``:
      ``/v1/chat/completions`` with same request/response format as OpenAI.
    * **High-throughput batching** — ``runtime/generation.py``: the server
      uses in-flight batching and KV cache paging internally.
    * **Model listing** — ``/v1/models`` returns loaded engine IDs.

What we replaced:
    * No TensorRT Python import — we only speak HTTP to the server.
    * ``httpx`` → stdlib ``urllib.request``.
    * GPU-only; not in standard CI.

OFFLINE tier: GPU inference, heavy resource requirements.
Cloud/GPU deployments only. LiteLLM routes to the TRT-LLM endpoint.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TensorRTResponse:
    """Parsed response from a TensorRT-LLM chat completion call."""

    content: str
    model: str = ""
    usage: Mapping[str, int] = field(default_factory=dict)
    error: str = ""


class TensorRTTransport:
    """HTTP transport to a TensorRT-LLM OpenAI-compatible server.

    Usage::

        transport = TensorRTTransport(base_url="http://localhost:8000")
        resp = transport.chat(
            model="llama-3-8b-trt",
            messages=[{"role": "user", "content": "hello"}],
        )
        print(resp.content)
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8000",
        api_key: str = "EMPTY",
        timeout_s: int = 120,
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
    ) -> TensorRTResponse:
        """Send a chat completion request to TensorRT-LLM server."""
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
            return TensorRTResponse(
                content=content,
                model=resp.get("model", model),
                usage=usage,
            )
        except Exception as e:
            return TensorRTResponse(content="", error=f"{type(e).__name__}: {e}")

    def list_models(self) -> list[str]:
        """List models loaded on the TensorRT-LLM server."""
        try:
            resp = self._get("/v1/models")
            data = resp.get("data", [])
            return [m.get("id", "") for m in data if isinstance(m, dict)]
        except Exception:
            return []

    def health(self) -> bool:
        """Check if the TensorRT-LLM server is reachable."""
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


__all__ = ["TensorRTResponse", "TensorRTTransport"]
