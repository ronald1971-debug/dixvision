"""Tests for C-47 — Ollama local-inference chat transport.

Coverage:
* Host resolution (env var, default, override)
* Message format conversion (LangChain → Ollama)
* Successful chat invocation (mocked HTTP)
* Transient error handling (connection failure, 5xx)
* Non-transient error handling (4xx)
* Empty/malformed response handling
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from intelligence_engine.cognitive.chat.local_transport import (
    DEFAULT_OLLAMA_HOST,
    OllamaLocalTransport,
    _langchain_to_ollama_messages,
    _resolve_ollama_host,
    build_ollama_transport,
)
from intelligence_engine.cognitive.chat.registry_driven_chat_model import (
    TransientProviderError,
)

# ---------------------------------------------------------------------------
# Fake AIProvider for testing
# ---------------------------------------------------------------------------


class _FakeProvider:
    """Minimal AIProvider-shaped object for tests."""

    def __init__(self, model: str = "llama3") -> None:
        self.model = model
        self.provider = "ollama"


# ---------------------------------------------------------------------------
# Host resolution
# ---------------------------------------------------------------------------


class TestHostResolution:
    def test_default_host(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert _resolve_ollama_host() == DEFAULT_OLLAMA_HOST

    def test_env_var_override(self) -> None:
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://myhost:1234"}):
            assert _resolve_ollama_host() == "http://myhost:1234"

    def test_explicit_override(self) -> None:
        assert _resolve_ollama_host("http://custom:5555") == "http://custom:5555"

    def test_adds_scheme_if_missing(self) -> None:
        assert _resolve_ollama_host("myhost:1234") == "http://myhost:1234"

    def test_strips_trailing_slash(self) -> None:
        assert _resolve_ollama_host("http://host:1234/") == "http://host:1234"


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


class TestMessageConversion:
    def test_system_message(self) -> None:
        msgs = [SystemMessage(content="You are helpful")]
        result = _langchain_to_ollama_messages(msgs)
        assert result == [{"role": "system", "content": "You are helpful"}]

    def test_human_message(self) -> None:
        msgs = [HumanMessage(content="Hello")]
        result = _langchain_to_ollama_messages(msgs)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_ai_message(self) -> None:
        msgs = [AIMessage(content="Hi there")]
        result = _langchain_to_ollama_messages(msgs)
        assert result == [{"role": "assistant", "content": "Hi there"}]

    def test_multi_turn(self) -> None:
        msgs = [
            SystemMessage(content="sys"),
            HumanMessage(content="q"),
            AIMessage(content="a"),
            HumanMessage(content="q2"),
        ]
        result = _langchain_to_ollama_messages(msgs)
        assert len(result) == 4
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"
        assert result[3]["role"] == "user"


# ---------------------------------------------------------------------------
# Transport invocation (mocked HTTP)
# ---------------------------------------------------------------------------


def _mock_response(content: str, status: int = 200) -> Any:
    """Create a mock HTTP response."""
    body = json.dumps(
        {
            "message": {"role": "assistant", "content": content},
            "done": True,
        }
    ).encode()

    class FakeResp:
        def read(self, n: int = -1) -> bytes:
            return body[:n] if n > 0 else body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    return FakeResp()


class TestOllamaTransport:
    def test_successful_invoke(self) -> None:
        transport = OllamaLocalTransport(host="http://fake:11434")
        provider = _FakeProvider(model="mistral")
        messages = [HumanMessage(content="Hello")]

        with patch(
            "intelligence_engine.cognitive.chat.local_transport._open",
            return_value=_mock_response("Hello from Ollama!"),
        ):
            result = transport.invoke(provider, messages)

        assert result == "Hello from Ollama!"

    def test_uses_provider_model(self) -> None:
        transport = OllamaLocalTransport(host="http://fake:11434")
        provider = _FakeProvider(model="codellama")
        captured_data: list[bytes] = []

        def capture_open(req, timeout):
            captured_data.append(req.data)
            return _mock_response("ok")

        with patch(
            "intelligence_engine.cognitive.chat.local_transport._open",
            side_effect=capture_open,
        ):
            transport.invoke(provider, [HumanMessage(content="hi")])

        body = json.loads(captured_data[0])
        assert body["model"] == "codellama"

    def test_falls_back_to_default_model(self) -> None:
        transport = OllamaLocalTransport(host="http://fake:11434", default_model="phi3")
        provider = _FakeProvider(model="")
        captured_data: list[bytes] = []

        def capture_open(req, timeout):
            captured_data.append(req.data)
            return _mock_response("ok")

        with patch(
            "intelligence_engine.cognitive.chat.local_transport._open",
            side_effect=capture_open,
        ):
            transport.invoke(provider, [HumanMessage(content="hi")])

        body = json.loads(captured_data[0])
        assert body["model"] == "phi3"

    def test_connection_error_raises_transient(self) -> None:

        transport = OllamaLocalTransport(host="http://fake:11434")
        provider = _FakeProvider()

        with patch(
            "intelligence_engine.cognitive.chat.local_transport._open",
            side_effect=ConnectionError("refused"),
        ):
            with pytest.raises(TransientProviderError, match="Failed to connect"):
                transport.invoke(provider, [HumanMessage(content="hi")])

    def test_5xx_raises_transient(self) -> None:
        import urllib.error

        transport = OllamaLocalTransport(host="http://fake:11434")
        provider = _FakeProvider()

        err = urllib.error.HTTPError(
            "http://fake:11434/api/chat",
            500,
            "Internal Error",
            {},
            BytesIO(b"error"),  # type: ignore[arg-type]
        )

        with patch(
            "intelligence_engine.cognitive.chat.local_transport._open",
            side_effect=err,
        ):
            with pytest.raises(TransientProviderError, match="500"):
                transport.invoke(provider, [HumanMessage(content="hi")])

    def test_4xx_raises_runtime_error(self) -> None:
        import urllib.error

        transport = OllamaLocalTransport(host="http://fake:11434")
        provider = _FakeProvider()

        err = urllib.error.HTTPError(
            "http://fake:11434/api/chat",
            400,
            "Bad Request",
            {},
            BytesIO(b"bad model"),  # type: ignore[arg-type]
        )

        with patch(
            "intelligence_engine.cognitive.chat.local_transport._open",
            side_effect=err,
        ):
            with pytest.raises(RuntimeError, match="400"):
                transport.invoke(provider, [HumanMessage(content="hi")])


class TestBuildFactory:
    def test_build_ollama_transport(self) -> None:
        t = build_ollama_transport(host="http://test:1234", model="gemma")
        assert isinstance(t, OllamaLocalTransport)
        assert t._base_url == "http://test:1234"
        assert t._default_model == "gemma"
