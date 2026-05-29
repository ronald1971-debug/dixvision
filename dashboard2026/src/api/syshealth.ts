const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export interface ComponentStatus {
  name: string;
  status: "ok" | "degraded" | "error" | "unknown";
  detail?: string;
  latency_ms?: number;
}

export interface SysHealthPayload {
  components: ComponentStatus[];
  dead_man?: { active: boolean; last_heartbeat_utc: string; ttl_sec: number };
  latency_guard?: { breached: boolean; p99_ms: number; threshold_ms: number };
  ts_utc?: string;
}

export async function fetchSysHealth(signal?: AbortSignal): Promise<SysHealthPayload> {
  const res = await fetch(`${BASE}/api/syshealth`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/syshealth failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SysHealthPayload;
}
