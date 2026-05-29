const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export interface VoiceAlertRecord {
  output_path: string;
  duration_seconds: number;
  model_used: string;
}

export interface VoiceAlertsPayload {
  min_severity: string;
  dispatched_count: number;
  history: VoiceAlertRecord[];
}

export async function fetchVoiceAlerts(signal?: AbortSignal): Promise<VoiceAlertsPayload> {
  const res = await fetch(`${BASE}/api/voice-alerts`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/voice-alerts failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as VoiceAlertsPayload;
}

export async function dispatchVoiceAlert(body: {
  severity: string;
  message: string;
  governance_mode?: string;
}): Promise<{ dispatched: boolean; reason?: string; output_path?: string; duration_seconds?: number }> {
  const res = await fetch(`${BASE}/api/voice-alerts/dispatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      severity: body.severity,
      message: body.message,
      governance_mode: body.governance_mode ?? "UNKNOWN",
    }),
  });
  if (!res.ok) {
    throw new Error(`POST /api/voice-alerts/dispatch failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as { dispatched: boolean; reason?: string; output_path?: string; duration_seconds?: number };
}
