import { useEffect, useRef, useState } from "react";

import { apiUrl } from "@/api/base";

/**
 * Cognitive intelligence real-time bridge.
 *
 * Connects to ``GET /api/cognitive/stream`` (SSE) which fans out:
 *   channel "indira" — INTELLIGENCE/INDIRA ledger events
 *   channel "dyon"   — SYSTEM/DYON ledger events
 *
 * Falls back to seed data when the endpoint is unreachable (dev / no
 * backend). Widgets stay rendered and informative in both modes.
 *
 * Wire format from backend:
 *   data: {"channel": "indira"|"dyon", "ts_iso": "...", "payload": {...}}
 */

export interface CognitiveStreamEvent<T = unknown> {
  channel: "indira" | "dyon";
  ts_iso: string;
  payload: T;
}

type CogListener<T> = (event: CognitiveStreamEvent<T>) => void;

const _listeners = new Map<string, Set<CogListener<unknown>>>();
let _source: EventSource | null = null;
let _connectionState: "idle" | "live" | "mock" = "idle";
const _stateListeners = new Set<(s: typeof _connectionState) => void>();

function _setConnectionState(s: typeof _connectionState) {
  if (s === _connectionState) return;
  _connectionState = s;
  for (const fn of _stateListeners) fn(s);
}

function _dispatch(event: CognitiveStreamEvent) {
  const set = _listeners.get(event.channel);
  if (!set) return;
  for (const fn of set) {
    try {
      fn(event);
    } catch {
      // never let one widget crash break the bus
    }
  }
}

function _ensureConnected() {
  if (_source) return;
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    _setConnectionState("mock");
    return;
  }
  try {
    _source = new EventSource(apiUrl("/api/cognitive/stream"));
    _source.onopen = () => _setConnectionState("live");
    _source.onerror = () => {
      _source?.close();
      _source = null;
      _setConnectionState("mock");
    };
    _source.onmessage = (e: MessageEvent) => {
      if (!e.data || e.data.startsWith(":")) return; // SSE comment / keepalive
      try {
        const parsed = JSON.parse(e.data) as CognitiveStreamEvent;
        _dispatch(parsed);
      } catch {
        // ignore malformed payload
      }
    };
  } catch {
    _setConnectionState("mock");
  }
}

/**
 * Subscribe to one cognitive channel ("indira" | "dyon").
 * Returns the last `cap` payloads received, newest-last.
 * When connection is in "mock" mode no events arrive and the widget
 * keeps its own seed data.
 */
export function useCognitiveStream<T = unknown>(
  channel: "indira" | "dyon",
  cap = 100,
): { events: T[]; live: boolean } {
  const [events, setEvents] = useState<T[]>([]);
  const [live, setLive] = useState(false);
  const capRef = useRef(cap);
  capRef.current = cap;

  useEffect(() => {
    _ensureConnected();

    const onState = (s: typeof _connectionState) => setLive(s === "live");
    _stateListeners.add(onState);
    setLive(_connectionState === "live");

    const listener: CogListener<unknown> = (evt) => {
      setEvents((prev) => {
        const next = [...prev, evt.payload as T];
        return next.length > capRef.current
          ? next.slice(next.length - capRef.current)
          : next;
      });
    };

    let set = _listeners.get(channel);
    if (!set) {
      set = new Set();
      _listeners.set(channel, set);
    }
    set.add(listener as CogListener<unknown>);

    return () => {
      set?.delete(listener as CogListener<unknown>);
      _stateListeners.delete(onState);
    };
  }, [channel]);

  return { events, live };
}
