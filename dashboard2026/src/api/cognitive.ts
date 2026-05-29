/**
 * Cognitive intelligence API fetchers — INDIRA + DYON observability surfaces.
 *
 * Covers:
 *   GET /api/cognitive/indira/thoughts
 *   GET /api/cognitive/indira/beliefs
 *   GET /api/cognitive/dyon/topology
 *   GET /api/cognitive/dyon/proposals
 *   GET /api/cognitive/research/status
 *   GET /api/cognitive/research/results
 *   POST /api/cognitive/research/enqueue
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

// ---------------------------------------------------------------------------
// INDIRA
// ---------------------------------------------------------------------------

export interface ThoughtRecord {
  thought_id?: string;
  ts_ns?: number;
  sub_type?: string;
  payload?: {
    reasoning_step?: string;
    context?: string;
    conclusion?: string;
    confidence?: number;
  };
}

export interface ThoughtsResponse {
  ts_iso: string;
  count: number;
  thoughts: ThoughtRecord[];
}

export function fetchIndiraThoughts(
  limit = 20,
  signal?: AbortSignal,
): Promise<ThoughtsResponse> {
  return _get<ThoughtsResponse>(
    `/api/cognitive/indira/thoughts?limit=${limit}`,
    signal,
  );
}

export interface BeliefRecord {
  ts_ns?: number;
  payload?: {
    subject?: string;
    old_value?: number;
    new_value?: number;
    driver?: string;
    confidence?: number;
  };
}

export interface BeliefsResponse {
  ts_iso: string;
  count: number;
  beliefs: BeliefRecord[];
}

export function fetchIndiraBeliefs(
  limit = 20,
  signal?: AbortSignal,
): Promise<BeliefsResponse> {
  return _get<BeliefsResponse>(
    `/api/cognitive/indira/beliefs?limit=${limit}`,
    signal,
  );
}

// ---------------------------------------------------------------------------
// DYON
// ---------------------------------------------------------------------------

export interface TopologyViolation {
  invariant_id: string;
  rule: string;
  source_module: string;
  imported_module: string;
  line: number;
  severity: "CRITICAL" | "WARNING";
  description: string;
}

export interface TopologyResponse {
  ts_ns?: number;
  root?: string;
  files_scanned: number;
  scan_duration_ms?: number;
  violation_count: number;
  critical_count?: number;
  warning_count?: number;
  clean: boolean;
  violations: TopologyViolation[];
  status?: string;
  error?: string;
}

export function fetchDyonTopology(
  signal?: AbortSignal,
): Promise<TopologyResponse> {
  return _get<TopologyResponse>("/api/cognitive/dyon/topology", signal);
}

export interface PatchProposalRecord {
  proposal_id?: string;
  ts_ns?: number;
  invariant_id?: string;
  source_module?: string;
  imported_module?: string;
  severity?: string;
  description?: string;
  recommended_action?: string;
  payload?: Record<string, unknown>;
}

export interface ProposalsResponse {
  ts_iso: string;
  count: number;
  proposals: PatchProposalRecord[];
}

export function fetchDyonProposals(
  limit = 50,
  signal?: AbortSignal,
): Promise<ProposalsResponse> {
  return _get<ProposalsResponse>(
    `/api/cognitive/dyon/proposals?limit=${limit}`,
    signal,
  );
}

// ---------------------------------------------------------------------------
// Autonomous Research
// ---------------------------------------------------------------------------

export interface ResearchQueueItem {
  topic: string;
  priority: number;
  task_type: string;
}

export interface ResearchStatusResponse {
  ts_iso?: string;
  running: boolean;
  queue_depth: number;
  queue_preview: ResearchQueueItem[];
  total_runs: number;
  total_ok: number;
  fetch_interval_s: number;
  recent_count: number;
}

export function fetchResearchStatus(
  signal?: AbortSignal,
): Promise<ResearchStatusResponse> {
  return _get<ResearchStatusResponse>(
    "/api/cognitive/research/status",
    signal,
  );
}

export interface ResearchResult {
  topic: string;
  task_type: string;
  status: string;
  pages_fetched: number;
  confidence: number;
  trust_score: number;
  sources: string[];
  ts_ns: number;
}

export interface ResearchResultsResponse {
  ts_iso: string;
  count: number;
  results: ResearchResult[];
}

export function fetchResearchResults(
  limit = 20,
  signal?: AbortSignal,
): Promise<ResearchResultsResponse> {
  return _get<ResearchResultsResponse>(
    `/api/cognitive/research/results?limit=${limit}`,
    signal,
  );
}

export interface EnqueueRequest {
  topic: string;
  task_type?: string;
  target_urls?: string[];
  max_pages?: number;
  priority?: number;
}

export interface EnqueueResponse {
  ts_iso: string;
  topic: string;
  task_type: string;
  priority: number;
  queue_depth: number;
  message: string;
}

// ---------------------------------------------------------------------------
// Cognitive Snapshot — unified orchestrator health
// ---------------------------------------------------------------------------

export interface CognitiveSnapshotResponse {
  ts_iso: string;
  evolution?: {
    orchestrator: string;
    tick_count: number;
    structural_loop_wired: boolean;
    critique_loop_wired: boolean;
    arena_wired: boolean;
    dyon?: {
      tick_count: number;
      scan_count: number;
      scan_interval: number;
    };
  };
  indira?: {
    intelligence: string;
    tick_count: number;
    cycle_position: number;
    runtime: string;
  };
  memory?: {
    episodic_size: number;
    semantic_size: number;
    procedural_size: number;
    consolidate_seq: number;
  };
  research?: {
    running: boolean;
    queue_depth: number;
    total_runs: number;
    total_ok?: number;
  };
}

export function fetchCognitiveSnapshot(
  signal?: AbortSignal,
): Promise<CognitiveSnapshotResponse> {
  return _get<CognitiveSnapshotResponse>("/api/cognitive/snapshot", signal);
}

export async function postResearchEnqueue(
  body: EnqueueRequest,
): Promise<EnqueueResponse> {
  const res = await fetch(`${BASE}/api/cognitive/research/enqueue`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST /api/cognitive/research/enqueue failed: ${res.status}`);
  return res.json() as Promise<EnqueueResponse>;
}
