/**
 * Unified Cognitive Memory Layer API fetchers.
 *
 * Covers all 11 endpoints under /api/memory/*.
 */

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function _get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

// ─── Snapshot ────────────────────────────────────────────────────────────────

export interface MemoryKindCounts {
  EPISODIC?: number;
  SEMANTIC?: number;
  PROCEDURAL?: number;
  STRATEGY?: number;
  TRADER?: number;
  GOVERNANCE?: number;
  RUNTIME?: number;
  REGRET?: number;
  [key: string]: number | undefined;
}

export interface MemorySnapshotResponse {
  active?: boolean;
  timeline_count?: number;
  index_size?: number;
  dedup_cache_size?: number;
  compressor_buffer_size?: number;
  stores?: MemoryKindCounts;
  ts_iso?: string;
}

export function fetchMemoryLayerSnapshot(
  signal?: AbortSignal,
): Promise<MemorySnapshotResponse> {
  return _get<MemorySnapshotResponse>("/api/memory/snapshot", signal);
}

// ─── Timeline ────────────────────────────────────────────────────────────────

export interface MemoryRecordEntry {
  record_id: string;
  kind: string;
  ts_ns: number;
  source: string;
  summary: string;
  tags?: string[];
  confidence?: number;
  parent_id?: string;
}

export interface MemoryTimelineResponse {
  count: number;
  records: MemoryRecordEntry[];
  persisted?: number;
}

export function fetchMemoryTimeline(
  limit = 50,
  since_ns = 0,
  kind = "",
  signal?: AbortSignal,
): Promise<MemoryTimelineResponse> {
  const p = new URLSearchParams({ limit: String(limit) });
  if (since_ns) p.set("since_ns", String(since_ns));
  if (kind) p.set("kind", kind);
  return _get<MemoryTimelineResponse>(`/api/memory/timeline?${p}`, signal);
}

// ─── Search ──────────────────────────────────────────────────────────────────

export interface MemorySearchResponse {
  query?: string;
  mode?: string;
  count: number;
  records: MemoryRecordEntry[];
}

export function fetchMemorySearch(
  q: string,
  limit = 20,
  mode: "all" | "any" = "all",
  signal?: AbortSignal,
): Promise<MemorySearchResponse> {
  const p = new URLSearchParams({ q, limit: String(limit), mode });
  return _get<MemorySearchResponse>(`/api/memory/search?${p}`, signal);
}

// ─── Identity ────────────────────────────────────────────────────────────────

export interface MemoryIdentityResponse {
  cache_size?: number;
  cache_capacity?: number;
  total_assigned?: number;
  total_new?: number;
  total_dedup?: number;
}

export function fetchMemoryIdentity(
  signal?: AbortSignal,
): Promise<MemoryIdentityResponse> {
  return _get<MemoryIdentityResponse>("/api/memory/identity", signal);
}

// ─── Compression ─────────────────────────────────────────────────────────────

export interface MemoryCompressionResponse {
  total_compressed?: number;
  dedup_skips?: number;
  buffer_size?: number;
  min_group_size?: number;
}

export function fetchMemoryCompression(
  signal?: AbortSignal,
): Promise<MemoryCompressionResponse> {
  return _get<MemoryCompressionResponse>("/api/memory/compression", signal);
}

// ─── Replay sessions ─────────────────────────────────────────────────────────

export interface MemoryReplaySession {
  session_id: string;
  since_ns?: number;
  until_ns?: number;
  batch_size?: number;
  cursor_ns?: number;
  exhausted?: boolean;
  batches_served?: number;
}

export interface MemoryReplaySessionsResponse {
  active_count?: number;
  total_sessions?: number;
  sessions: MemoryReplaySession[];
}

export function fetchMemoryReplaySessions(
  signal?: AbortSignal,
): Promise<MemoryReplaySessionsResponse> {
  return _get<MemoryReplaySessionsResponse>("/api/memory/replay/sessions", signal);
}

// ─── Domain stores ───────────────────────────────────────────────────────────

export interface StoreMiniRecord {
  record_id: string;
  summary: string;
  ts_ns: number;
}

export interface MemoryStrategyStoreResponse {
  proposal_count?: number;
  fitness_history_size?: number;
  recent?: StoreMiniRecord[];
}

export function fetchMemoryStrategyStore(
  limit = 20,
  signal?: AbortSignal,
): Promise<MemoryStrategyStoreResponse> {
  return _get<MemoryStrategyStoreResponse>(
    `/api/memory/stores/strategy?limit=${limit}`,
    signal,
  );
}

export interface MemoryTraderStoreResponse {
  trader_count?: number;
  leaderboard?: unknown[];
  recent?: StoreMiniRecord[];
}

export function fetchMemoryTraderStore(
  limit = 20,
  signal?: AbortSignal,
): Promise<MemoryTraderStoreResponse> {
  return _get<MemoryTraderStoreResponse>(
    `/api/memory/stores/trader?limit=${limit}`,
    signal,
  );
}

export interface MemoryGovernanceStoreResponse {
  mode_transition_count?: number;
  violation_count?: number;
  operator_action_count?: number;
  mode_history?: string[];
  recent?: StoreMiniRecord[];
}

export function fetchMemoryGovernanceStore(
  limit = 20,
  signal?: AbortSignal,
): Promise<MemoryGovernanceStoreResponse> {
  return _get<MemoryGovernanceStoreResponse>(
    `/api/memory/stores/governance?limit=${limit}`,
    signal,
  );
}

export interface MemoryRuntimeStoreResponse {
  health_event_count?: number;
  failure_count?: number;
  recovery_count?: number;
  recent?: StoreMiniRecord[];
}

export function fetchMemoryRuntimeStore(
  limit = 20,
  signal?: AbortSignal,
): Promise<MemoryRuntimeStoreResponse> {
  return _get<MemoryRuntimeStoreResponse>(
    `/api/memory/stores/runtime?limit=${limit}`,
    signal,
  );
}
