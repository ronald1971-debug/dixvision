# ADAPTED FROM: ollama/ollama-python
# (ollama/_client.py — Client class, BaseClient host resolution, _parse_host,
#  chat() method with model/messages/stream/format/options/keep_alive params;
#  ollama/_types.py — ChatRequest, ChatResponse, Message, Options, ResponseError.)
"""C-47 — Ollama local-inference chat transport.

This module adapts the ``ollama-python`` client library
(https://github.com/ollama/ollama-python, MIT License) as a local
inference transport for the chat layer. It speaks to a locally running
Ollama server (default http://localhost:11434) using the ``/api/chat``
endpoint — the same protocol as the official Python client.

What survives from upstream (ollama/ollama-python):

* **Host resolution** — ``_client.py:113``: ``_parse_host`` logic that
  reads ``OLLAMA_HOST`` env var or defaults to ``http://localhost:11434``.
  We reproduce this as ``_resolve_ollama_host()``.
* **Chat request schema** — ``_types.py ChatRequest``: the JSON body
  sent to ``/api/chat`` with fields ``model``, ``messages``, ``stream``,
  ``format``, ``options``, ``keep_alive``. We build the same structure.
* **Message format** — ``_types.py Message``: each message is
  ``{"role": ..., "content": ...}`` matching Ollama's expected format.
* **Response parsing** — non-streaming response is a single JSON object
  with ``message.content`` holding the assistant's reply text.
* **Error handling** — ``_client.py:143-145``: ``ResponseError`` on HTTP
  errors, ``ConnectionError`` with descriptive message on connect failure.

What we replaced:

* ``httpx`` dependency → stdlib ``urllib.request`` (matching the existing
  ``http_chat_transport.py`` pattern in this package — avoids adding
  httpx as a runtime dep).
* ``pydantic`` model serialization → plain ``json.dumps`` of a dict.
* Streaming support → not implemented (chat layer uses single-turn).
* ``anyio`` async → synchronous only (matching ChatTransport Protocol).

DIX integration rules:

* Same ChatTransport Protocol as existing transports.
* B1 + B24 isolation: imports only ``langchain_core`` types and
  ``core.cognitive_router.AIProvider``.
* Stdlib HTTP only (``urllib.request``), same as ``http_chat_transport``.
* No secret exposure in error messages.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Final

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from core.cognitive_router import AIProvider
from intelligence_engine.cognitive.chat.registry_driven_chat_model import (
    TransientProviderError,
)

__all__ = [
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_TIMEOUT_S",
    "OllamaLocalTransport",
    "build_ollama_transport",
]


DEFAULT_OLLAMA_HOST: Final[str] = "http://localhost:11434"
"""Default Ollama server address (matches ollama-python _client.py)."""

DEFAULT_TIMEOUT_S: Final[float] = 120.0
"""Timeout for local inference (higher than cloud — local models are slower)."""

MAX_RESPONSE_BYTES: Final[int] = 8 * 1024 * 1024  # 8 MiB
"""Hard cap on response body read size."""


# ---------------------------------------------------------------------------
# Host resolution (mirrors ollama/_client.py _parse_host)
# ---------------------------------------------------------------------------


def _resolve_ollama_host(override: str | None = None) -> str:
    """Resolve the Ollama server base URL.

    Priority:
    1. Explicit override parameter
    2. OLLAMA_HOST environment variable
    3. Default localhost:11434

    Mirrors ollama-python's _parse_host() logic from _client.py:113.
    """
    host = override or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST

    # Ensure scheme is present (ollama-python adds http:// if missing)
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"

    # Strip trailing slash
    return host.rstrip("/")


# ---------------------------------------------------------------------------
# Message conversion (mirrors ollama/_types.py Message format)
# ---------------------------------------------------------------------------


def _langchain_to_ollama_messages(
    messages: Sequence[BaseMessage],
) -> list[dict[str, str]]:
    """Convert LangChain messages to Ollama's message format.

    Ollama expects: [{"role": "system"|"user"|"assistant", "content": "..."}]
    Same format as ollama-python's Message dataclass.
    """
    result: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "system"
        elif isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        else:
            role = "user"
        result.append({"role": role, "content": str(msg.content)})
    return result


# ---------------------------------------------------------------------------
# HTTP execution (mirrors ollama/_client.py Client._request_raw + chat)
# ---------------------------------------------------------------------------


def _open(
    request: urllib.request.Request,
    timeout: float,
):
    """Indirection over urlopen for test monkey-patching."""
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def _execute_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    options: Mapping[str, Any] | None = None,
    keep_alive: str | None = None,
) -> str:
    """Execute a chat request against the Ollama /api/chat endpoint.

    Mirrors ollama-python Client.chat() method from _client.py:340-405.

    Args:
        base_url: Ollama server base URL.
        model: Model name (e.g. "llama3", "mistral").
        messages: Ollama-format message list.
        timeout: HTTP timeout in seconds.
        options: Model options (temperature, top_p, etc).
        keep_alive: How long to keep model loaded ("5m", "0", etc).

    Returns:
        Assistant's reply text.

    Raises:
        TransientProviderError: On connection failure or 5xx.
        RuntimeError: On 4xx or malformed response.
    """
    # Build request body matching ollama ChatRequest schema
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if options:
        body["options"] = dict(options)
    if keep_alive is not None:
        body["keep_alive"] = keep_alive

    url = f"{base_url}/api/chat"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        resp = _open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        status = e.code
        detail = ""
        try:
            err_body = e.read(4096).decode("utf-8", errors="replace")
            detail = err_body[:200]
        except Exception:
            pass
        if status == 429 or (500 <= status <= 599):
            raise TransientProviderError(f"Ollama server returned {status}: {detail}") from None
        raise RuntimeError(f"Ollama request failed ({status}): {detail}") from None
    except (urllib.error.URLError, OSError, ConnectionError) as e:
        raise TransientProviderError(
            f"Failed to connect to Ollama at {base_url}: {type(e).__name__}"
        ) from None

    # Parse response (mirrors ollama-python's non-streaming path)
    raw = resp.read(MAX_RESPONSE_BYTES)
    try:
        data_resp = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise RuntimeError(f"Ollama returned malformed JSON: {type(e).__name__}") from None

    # Extract content from response (same path as ChatResponse in _types.py)
    if "error" in data_resp:
        raise RuntimeError(f"Ollama error: {data_resp['error']}")

    message = data_resp.get("message", {})
    content = message.get("content", "")
    if not content:
        raise RuntimeError("Ollama returned empty response content")

    return content


# ---------------------------------------------------------------------------
# ChatTransport implementation
# ---------------------------------------------------------------------------


class OllamaLocalTransport:
    """ChatTransport for locally-running Ollama server.

    Adapts the ollama-python Client.chat() pattern to the DIX
    ChatTransport Protocol, using stdlib HTTP.

    Args:
        host: Ollama server URL (default: OLLAMA_HOST env or localhost:11434).
        timeout: Request timeout in seconds.
        default_model: Model to use if provider row doesn't specify one.
        options: Default model options (temperature, etc).
    """

    def __init__(
        self,
        host: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        default_model: str = "llama3",
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self._base_url = _resolve_ollama_host(host)
        self._timeout = timeout
        self._default_model = default_model
        self._options = dict(options) if options else None

    def invoke(
        self,
        provider: AIProvider,
        messages: Sequence[BaseMessage],
        /,
        **kwargs: Any,
    ) -> str:
        """Send messages to local Ollama and return assistant's text.

        The model is determined by:
        1. ``provider.model`` field from registry row
        2. ``self._default_model`` fallback
        """
        model = getattr(provider, "model", None) or self._default_model
        ollama_messages = _langchain_to_ollama_messages(messages)

        return _execute_chat(
            base_url=self._base_url,
            model=model,
            messages=ollama_messages,
            timeout=self._timeout,
            options=self._options,
            keep_alive=kwargs.get("keep_alive"),
        )


# ---------------------------------------------------------------------------
# Factory (convenience)
# ---------------------------------------------------------------------------


def build_ollama_transport(
    host: str | None = None,
    *,
    model: str = "llama3",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> OllamaLocalTransport:
    """Build an OllamaLocalTransport with sensible defaults.

    This is the recommended entry point for wiring Ollama into the
    RegistryDispatchChatTransport's provider table.
    """
    return OllamaLocalTransport(
        host=host,
        timeout=timeout,
        default_model=model,
    )
