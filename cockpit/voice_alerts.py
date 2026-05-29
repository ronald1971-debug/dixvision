# ADAPTED FROM: coqui-ai/TTS
# (TTS/api.py — TTS.tts_to_file() invocation pattern;
#  alert-routing based on HazardEvent severity levels)
"""C-77 — Voice alert dispatcher for operator cockpit.

Bridges ``HazardEvent`` severity levels to spoken alerts via
``sensory/voice/synthesizer.py``. Only CRITICAL+ events trigger audio.

Rules:
    * TTS output-only — no feedback into RUNTIME logic.
    * Only ``HazardEvent`` severity >= CRITICAL triggers audio alert.
    * Local synthesis — no cloud TTS API.
    * Spoken alerts carry governance mode context.
"""

from __future__ import annotations

from dataclasses import dataclass

from sensory.voice.synthesizer import (
    ALERT_TEMPLATES,
    SynthesisRequest,
    SynthesisResult,
    VoiceSynthesizer,
)


@dataclass(frozen=True, slots=True)
class VoiceAlertEvent:
    """A voice alert triggered by a hazard event."""

    severity: str
    message: str
    governance_mode: str = "UNKNOWN"


class VoiceAlertDispatcher:
    """Dispatches voice alerts based on HazardEvent severity.

    Only CRITICAL and HIGH severity events produce spoken alerts.
    """

    MINIMUM_SEVERITY = "CRITICAL"
    _SEVERITY_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL", "FATAL")

    def __init__(
        self,
        *,
        synthesizer: VoiceSynthesizer | None = None,
        min_severity: str = "CRITICAL",
    ) -> None:
        self._synthesizer = synthesizer or VoiceSynthesizer(in_memory=True)
        self._min_severity = min_severity
        self._dispatched: list[SynthesisResult] = []

    def dispatch(self, event: VoiceAlertEvent) -> SynthesisResult | None:
        """Dispatch a voice alert if severity meets threshold.

        Returns the synthesis result if alert was spoken, None otherwise.
        """
        if not self._severity_meets_threshold(event.severity):
            return None

        text = self._format_alert(event)
        request = SynthesisRequest(text=text)
        result = self._synthesizer.synthesize(request)
        self._dispatched.append(result)
        return result

    @property
    def dispatched_alerts(self) -> list[SynthesisResult]:
        """All alerts that were actually spoken."""
        return list(self._dispatched)

    def _severity_meets_threshold(self, severity: str) -> bool:
        """Check if severity meets minimum threshold for voice alert."""
        try:
            sev_idx = self._SEVERITY_ORDER.index(severity.upper())
            min_idx = self._SEVERITY_ORDER.index(self._min_severity.upper())
            return sev_idx >= min_idx
        except ValueError:
            return False

    def _format_alert(self, event: VoiceAlertEvent) -> str:
        """Format alert text from template."""
        for template in ALERT_TEMPLATES:
            if template.severity == event.severity.upper():
                return template.template.format(
                    message=event.message,
                    mode=event.governance_mode,
                )
        return f"{event.severity}: {event.message}"


_DISPATCHER: VoiceAlertDispatcher | None = None


def get_dispatcher(*, min_severity: str = "CRITICAL") -> VoiceAlertDispatcher:
    """Return the process-wide voice alert dispatcher singleton."""
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = VoiceAlertDispatcher(min_severity=min_severity)
    return _DISPATCHER


__all__ = ["VoiceAlertDispatcher", "VoiceAlertEvent", "get_dispatcher"]
