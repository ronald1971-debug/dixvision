const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";

export interface Alert {
  id: string;
  severity: AlertSeverity;
  title: string;
  detail: string;
  ts_utc: string;
  acknowledged: boolean;
  source?: string;
}

export interface AlertsPayload {
  alerts: Alert[];
  unacknowledged: number;
}

export async function fetchAlerts(
  limit = 50,
  signal?: AbortSignal,
): Promise<AlertsPayload> {
  const res = await fetch(`${BASE}/api/alerts?limit=${limit}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/alerts failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as AlertsPayload;
}
