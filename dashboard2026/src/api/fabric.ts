/**
 * Unified Event Fabric API fetchers.
 *
 * Covers all 11 endpoints under /api/fabric/*.
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

export interface FabricSnapshotResponse {
  active?: boolean;
  ts_iso?: string;
  components?: Record<string, unknown>;
}

export function fetchFabricSnapshot(
  signal?: AbortSignal,
): Promise<FabricSnapshotResponse> {
  return _get<FabricSnapshotResponse>("/api/fabric/snapshot", signal);
}

// ─── Authority ───────────────────────────────────────────────────────────────

export interface FabricAuthorityResponse {
  published?: number;
  routed?: number;
  failed?: number;
  subscriber_count?: number;
  sequence?: number;
  subscriptions?: Record<string, number>;
}

export function fetchFabricAuthority(
  signal?: AbortSignal,
): Promise<FabricAuthorityResponse> {
  return _get<FabricAuthorityResponse>("/api/fabric/authority", signal);
}

// ─── Tracing ─────────────────────────────────────────────────────────────────

export interface SpanRecord {
  span_id: string;
  trace_id: string;
  parent_span_id: string;
  event_id: string;
  domain: string;
  event_type: string;
  ts_ns: number;
  source: string;
}

export interface ActiveTrace {
  trace_id: string;
  span_count: number;
  first_ts_ns?: number;
  last_ts_ns?: number;
  domains?: string[];
}

export interface FabricTracingResponse {
  span_count?: number;
  trace_count?: number;
  active_traces?: ActiveTrace[];
  recent_spans?: SpanRecord[];
}

export function fetchFabricTracing(
  limit = 50,
  signal?: AbortSignal,
): Promise<FabricTracingResponse> {
  return _get<FabricTracingResponse>(
    `/api/fabric/tracing?limit=${limit}`,
    signal,
  );
}

// ─── Lineage ─────────────────────────────────────────────────────────────────

export interface CausalLinkRecord {
  cause_id: string;
  effect_id: string;
  ts_ns: number;
  kind: string;
}

export interface FabricLineageResponse {
  node_count?: number;
  link_count?: number;
  recent_links?: CausalLinkRecord[];
}

export function fetchFabricLineage(
  limit = 50,
  signal?: AbortSignal,
): Promise<FabricLineageResponse> {
  return _get<FabricLineageResponse>(
    `/api/fabric/lineage?limit=${limit}`,
    signal,
  );
}

// ─── Persistence ─────────────────────────────────────────────────────────────

export interface FabricPersistenceResponse {
  active?: boolean;
  appended_session?: number;
  persisted_total?: number;
  domain_counts?: Record<string, number>;
  db_path?: string;
}

export function fetchFabricPersistence(
  signal?: AbortSignal,
): Promise<FabricPersistenceResponse> {
  return _get<FabricPersistenceResponse>("/api/fabric/persistence", signal);
}

// ─── Bridges ─────────────────────────────────────────────────────────────────

export interface BridgeStatusRecord {
  active?: boolean;
  forwarded?: number;
  failed?: number;
  channels?: string[];
}

export interface FabricBridgesResponse {
  cognitive?: BridgeStatusRecord;
  execution?: BridgeStatusRecord;
}

export function fetchFabricBridges(
  signal?: AbortSignal,
): Promise<FabricBridgesResponse> {
  return _get<FabricBridgesResponse>("/api/fabric/bridges", signal);
}

// ─── Events (paginated WAL log) ───────────────────────────────────────────────

export interface FabricEvent {
  event_id: string;
  sequence: number;
  domain: string;
  event_type: string;
  ts_ns: number;
  source: string;
  priority: number;
  trace_id: string;
  parent_id: string;
  tags: string;
  payload: string;
}

export interface FabricEventsResponse {
  count: number;
  events: FabricEvent[];
}

export function fetchFabricEvents(
  limit = 50,
  since_ns = 0,
  domain = "",
  event_type = "",
  trace_id = "",
  signal?: AbortSignal,
): Promise<FabricEventsResponse> {
  const p = new URLSearchParams({ limit: String(limit) });
  if (since_ns) p.set("since_ns", String(since_ns));
  if (domain) p.set("domain", domain);
  if (event_type) p.set("event_type", event_type);
  if (trace_id) p.set("trace_id", trace_id);
  return _get<FabricEventsResponse>(`/api/fabric/events?${p}`, signal);
}
