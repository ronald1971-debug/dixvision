# ADAPTED FROM: ggerganov/llama.cpp (via abetlen/llama-cpp-python)
# (llama_cpp/llama.py — Llama class, __call__(), create_chat_completion();
#  llama_cpp/llama_grammar.py — LlamaGrammar for constrained generation;
#  llama_cpp/llama_types.py — ChatCompletionRequestMessage, CreateChatCompletionResponse)
"""C-49 — llama-cpp-python CPU-only GGUF inference transport.

This module wraps ``llama-cpp-python`` for CPU-only local inference of
GGUF models. Unlike C-47 (Ollama) and C-48 (vLLM) which require a
separate server, this transport can load models directly in-process for
edge deployments with no GPU.

What survives from upstream (abetlen/llama-cpp-python):
    * **Llama class** — ``llama.py:83``: model loading from GGUF file
      with ``n_ctx``, ``n_threads``, ``verbose`` params.
    * **create_chat_completion()** — ``llama.py:1644``: takes
      ``messages``, ``temperature``, ``max_tokens``, returns
      ``CreateChatCompletionResponse``.
    * **LlamaGrammar** — ``llama_grammar.py``: constrains output to
      valid JSON via GBNF grammar. Always produces valid DIX contracts.
    * **Chat format** — messages as ``[{"role": ..., "content": ...}]``
      matching the OpenAI chat format.

What we replaced:
    * Heavy ``llama-cpp-python`` import is lazy (only at first call).
      Module is importable without the dependency installed.
    * No GPU code paths — CPU deterministic only.
    * Timestamps from caller, never self-generated (INV-15).

OFFLINE tier: model loading + inference too heavy for RUNTIME hot path.
CPU deterministic — bit-identical across runs with same seed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LlamaResponse:
    """Parsed response from llama-cpp-python inference."""

    content: str
    model: str = ""
    usage: Mapping[str, int] = field(default_factory=dict)
    error: str = ""


class LlamaTransport:
    """In-process GGUF model inference via llama-cpp-python.

    Usage::

        transport = LlamaTransport(
            model_path="/models/llama-3-8b.Q4_K_M.gguf",
            n_ctx=4096,
        )
        resp = transport.chat(
            messages=[{"role": "user", "content": "hello"}],
        )
        print(resp.content)
    """

    def __init__(
        self,
        *,
        model_path: str = "",
        n_ctx: int = 4096,
        n_threads: int = 4,
        seed: int = 42,
        verbose: bool = False,
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._seed = seed
        self._verbose = verbose
        self._llm: Any = None

    def _ensure_model(self) -> Any:
        """Lazy-load the llama-cpp-python model on first use."""
        if self._llm is not None:
            return self._llm

        try:
            from llama_cpp import Llama
        except ImportError as e:
            msg = "llama-cpp-python not installed. Install with: pip install llama-cpp-python"
            raise ImportError(msg) from e

        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            seed=self._seed,
            verbose=self._verbose,
        )
        return self._llm

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        grammar: str | None = None,
    ) -> LlamaResponse:
        """Run chat completion on the loaded GGUF model.

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature (0.0 = greedy).
            max_tokens: Maximum tokens to generate.
            grammar: Optional GBNF grammar string for constrained
                generation (ensures valid JSON output).
        """
        try:
            llm = self._ensure_model()
        except ImportError as e:
            return LlamaResponse(content="", error=str(e))

        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if grammar is not None:
            try:
                from llama_cpp import LlamaGrammar

                kwargs["grammar"] = LlamaGrammar.from_string(grammar)
            except ImportError:
                pass

        try:
            resp = llm.create_chat_completion(**kwargs)
            choices = resp.get("choices", [])
            content = choices[0]["message"]["content"] if choices else ""
            usage = resp.get("usage", {})
            return LlamaResponse(
                content=content,
                model=self._model_path,
                usage=usage,
            )
        except Exception as e:
            return LlamaResponse(content="", error=f"{type(e).__name__}: {e}")

    def unload(self) -> None:
        """Release the model from memory."""
        self._llm = None


# Standard JSON GBNF grammar for constrained generation.
JSON_GRAMMAR = r"""
root   ::= object
value  ::= object | array | string | number | ("true" | "false" | "null") ws

object ::=
  "{" ws (
    string ":" ws value
    ("," ws string ":" ws value)*
  )? "}" ws

array  ::=
  "[" ws (
    value
    ("," ws value)*
  )? "]" ws

string ::=
  "\"" (
    [^\\"\x7F\x00-\x1F] |
    "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])
  )* "\"" ws

number ::= ("-"? ([0-9] | [1-9] [0-9]*)) ("." [0-9]+)? (("e" | "E") ("+" | "-")? [0-9]+)? ws

ws ::= ([ \t\n] ws)?
"""

__all__ = ["JSON_GRAMMAR", "LlamaResponse", "LlamaTransport"]
