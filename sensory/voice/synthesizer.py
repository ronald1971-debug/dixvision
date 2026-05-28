# ADAPTED FROM: coqui-ai/TTS
# (TTS/api.py — TTS class, tts_to_file(), tts();
#  TTS/utils/manage.py — ModelManager, model selection;
#  TTS/tts/models/vits.py — VITS fast inference model)
"""C-77 — Coqui TTS speech synthesizer for spoken system alerts.

This module adapts the ``coqui-ai/TTS`` library for local text-to-speech
synthesis. Alerts are generated offline — never cloud TTS.

What survives from upstream (coqui-ai/TTS):
    * **TTS class** — ``api.py``: ``TTS(model_name).tts_to_file(text, path)``
      for one-shot synthesis.
    * **Model selection** — VITS for real-time speed, Tacotron2 for quality.
    * **WAV output** — direct file write via ``tts_to_file()``.

What we replaced:
    * Real ``TTS`` import is lazy (Protocol seam).
    * In-memory mock synthesis for unit tests (no model download).
    * Only triggered by ``HazardEvent`` severity >= CRITICAL.

OFFLINE tier — synthesis never in hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """Request to synthesize speech from text."""

    text: str
    model_name: str = "tts_models/en/ljspeech/vits"
    speaker: str | None = None
    language: str = "en"


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Result of speech synthesis."""

    output_path: str
    duration_seconds: float = 0.0
    sample_rate: int = 22050
    model_used: str = ""


class VoiceSynthesizer:
    """Coqui TTS synthesizer for system alerts.

    Mirrors ``TTS.api.TTS`` — model loading and one-shot synthesis.

    In test mode (default), produces empty WAV stubs.
    """

    def __init__(
        self,
        *,
        model_name: str = "tts_models/en/ljspeech/vits",
        output_dir: str = "/tmp/dix_voice_alerts",
        in_memory: bool = True,
    ) -> None:
        self._model_name = model_name
        self._output_dir = output_dir
        self._in_memory = in_memory
        self._synthesis_log: list[SynthesisResult] = []
        self._tts: Any = None

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesize speech from text.

        Mirrors ``TTS.tts_to_file(text, file_path=...)``.
        """
        if self._in_memory:
            return self._mock_synthesize(request)
        return self._real_synthesize(request)

    @property
    def synthesis_log(self) -> list[SynthesisResult]:
        """All synthesis results produced."""
        return list(self._synthesis_log)

    # ---- internals -------------------------------------------------------

    def _mock_synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Mock synthesis for testing — no model needed."""
        word_count = len(request.text.split())
        duration = word_count * 0.4  # ~0.4s per word estimate
        output_path = f"{self._output_dir}/alert_{len(self._synthesis_log)}.wav"
        result = SynthesisResult(
            output_path=output_path,
            duration_seconds=duration,
            sample_rate=22050,
            model_used=request.model_name,
        )
        self._synthesis_log.append(result)
        return result

    def _real_synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Real synthesis via Coqui TTS library."""
        try:
            from TTS.api import TTS as CoquiTTS  # noqa: N811

            if self._tts is None:
                self._tts = CoquiTTS(model_name=request.model_name)

            Path(self._output_dir).mkdir(parents=True, exist_ok=True)
            output_path = f"{self._output_dir}/alert_{len(self._synthesis_log)}.wav"

            self._tts.tts_to_file(
                text=request.text,
                file_path=output_path,
                speaker=request.speaker,
                language=request.language,
            )

            result = SynthesisResult(
                output_path=output_path,
                duration_seconds=0.0,  # Would need wav inspection
                sample_rate=22050,
                model_used=request.model_name,
            )
            self._synthesis_log.append(result)
            return result
        except ImportError:
            return self._mock_synthesize(request)

    def _load_model(self) -> None:
        """Lazy-load the TTS model."""
        try:
            from TTS.api import TTS as CoquiTTS  # noqa: N811

            self._tts = CoquiTTS(model_name=self._model_name)
        except ImportError:
            pass


@dataclass(frozen=True, slots=True)
class AlertTemplate:
    """Pre-defined voice alert templates."""

    severity: str
    template: str
    priority: int = 0


# Standard alert templates for different severity levels
ALERT_TEMPLATES: list[AlertTemplate] = [
    AlertTemplate(
        severity="CRITICAL",
        template="CRITICAL: {message}. Governance mode: {mode}.",
        priority=100,
    ),
    AlertTemplate(
        severity="HIGH",
        template="HIGH ALERT: {message}.",
        priority=80,
    ),
    AlertTemplate(
        severity="MEDIUM",
        template="WARNING: {message}.",
        priority=50,
    ),
]


__all__ = [
    "ALERT_TEMPLATES",
    "AlertTemplate",
    "SynthesisRequest",
    "SynthesisResult",
    "VoiceSynthesizer",
]
