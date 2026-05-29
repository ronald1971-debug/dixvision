const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export interface ScoutCandidate {
  symbol: string;
  reason: string;
  score?: number;
  tags?: string[];
}

export interface ScoutPayload {
  started_utc: string;
  finished_utc: string;
  candidates: ScoutCandidate[];
  errors: string[];
}

export async function fetchScout(signal?: AbortSignal): Promise<ScoutPayload> {
  const res = await fetch(`${BASE}/api/scout`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET /api/scout failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as ScoutPayload;
}

export async function runScout(): Promise<ScoutPayload> {
  const res = await fetch(`${BASE}/api/scout/run`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`POST /api/scout/run failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as ScoutPayload;
}
