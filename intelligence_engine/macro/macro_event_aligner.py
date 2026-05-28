"""MAC-04 — aligns macro calendar releases to price bars.

Pure function. No I/O. INV-15. B1 compliant.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["MacroEvent", "AlignedMacroEvent", "MacroEventAligner"]


@dataclass(frozen=True, slots=True)
class MacroEvent:
    event_id: str
    ts_ns: int         # scheduled release timestamp
    name: str
    importance: str    # "HIGH", "MEDIUM", "LOW"
    actual: float | None = None
    forecast: float | None = None
    prior: float | None = None


@dataclass(frozen=True, slots=True)
class AlignedMacroEvent:
    event: MacroEvent
    bar_index: int     # bar index relative to bar_start_ns
    offset_ns: int     # (event.ts_ns - bar_start_ns) within the bar
    surprise: float    # actual - forecast; 0.0 if missing


class MacroEventAligner:
    """Align macro events to OHLCV bar indices.

    Given a bar grid (start_ns, bar_size_ns) and a list of events,
    returns AlignedMacroEvent for each event that falls within the
    requested window.
    """

    def align(
        self,
        events: list[MacroEvent],
        *,
        window_start_ns: int,
        window_end_ns: int,
        bar_size_ns: int,
    ) -> tuple[AlignedMacroEvent, ...]:
        results: list[AlignedMacroEvent] = []
        for event in events:
            if not (window_start_ns <= event.ts_ns < window_end_ns):
                continue
            offset = event.ts_ns - window_start_ns
            bar_idx = int(offset // bar_size_ns)
            bar_offset = offset % bar_size_ns
            surprise = 0.0
            if event.actual is not None and event.forecast is not None:
                surprise = event.actual - event.forecast
            results.append(AlignedMacroEvent(
                event=event,
                bar_index=bar_idx,
                offset_ns=bar_offset,
                surprise=surprise,
            ))
        return tuple(sorted(results, key=lambda r: r.event.ts_ns))
