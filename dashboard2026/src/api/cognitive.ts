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

// ---------------------------------------------------------------------------
// Stage 2 — INDIRA Consciousness Stream
// ---------------------------------------------------------------------------

export interface ConsciousnessEntry {
  entry_id: string;
  ts_ns: number;
  event_kind: string;
  narrative: string;
  importance: number;
  source: string;
  raw_sub_type: string;
}

export interface ConsciousnessResponse {
  count: number;
  entries: ConsciousnessEntry[];
  ts_iso?: string;
}

export function fetchIndiraConsciousness(
  limit = 50,
  signal?: AbortSignal,
): Promise<ConsciousnessResponse> {
  return _get<ConsciousnessResponse>(
    `/api/cognitive/indira/consciousness?limit=${limit}`,
    signal,
  );
}

export interface CausalHypothesisRecord {
  hypo_id: string;
  label: string;
  state: string;
  confidence: number;
  evidence_count: number;
  age_ticks: number;
  ts_ns?: number;
}

export interface CausalResponse {
  active_hypotheses: CausalHypothesisRecord[];
  top_chain?: { label: string; confidence: number } | null;
  stats?: Record<string, unknown>;
  ts_iso?: string;
}

export function fetchIndiraCausal(
  signal?: AbortSignal,
): Promise<CausalResponse> {
  return _get<CausalResponse>("/api/cognitive/indira/causal", signal);
}

export interface BehavioralClusterRecord {
  cluster_id: string;
  label: string;
  strength: number;
  composite_score: number;
  member_count: number;
  dominant?: boolean;
}

export interface ClustersResponse {
  dominant_cluster?: BehavioralClusterRecord | null;
  clusters: BehavioralClusterRecord[];
  ts_iso?: string;
}

export function fetchIndiraClusters(
  signal?: AbortSignal,
): Promise<ClustersResponse> {
  return _get<ClustersResponse>("/api/cognitive/indira/clusters", signal);
}

export interface ObservationSessionRecord {
  session_id: string;
  focus_label: string;
  theme: string;
  state: string;
  tick_age: number;
  hypothesis_count: number;
}

export interface ObservationsResponse {
  active_count: number;
  sessions: ObservationSessionRecord[];
  ts_iso?: string;
}

export function fetchIndiraObservations(
  signal?: AbortSignal,
): Promise<ObservationsResponse> {
  return _get<ObservationsResponse>("/api/cognitive/indira/observations", signal);
}

// ---------------------------------------------------------------------------
// Stage 3 — DYON Engineering Workspace
// ---------------------------------------------------------------------------

export interface DyonWorkspaceResponse {
  workspace: string;
  grade?: string;
  health_score?: number;
  active?: boolean;
  panels?: Record<string, unknown>;
  ts_iso?: string;
}

export function fetchDyonWorkspace(
  signal?: AbortSignal,
): Promise<DyonWorkspaceResponse> {
  return _get<DyonWorkspaceResponse>("/api/cognitive/dyon/workspace", signal);
}

export interface DyonEngineeringResponse {
  runtime?: string;
  active?: boolean;
  tick_seq?: number;
  phase_errors?: Record<string, number>;
  latest_report?: Record<string, unknown>;
  subsystems?: Record<string, unknown>;
  ts_iso?: string;
}

export function fetchDyonEngineering(
  signal?: AbortSignal,
): Promise<DyonEngineeringResponse> {
  return _get<DyonEngineeringResponse>("/api/cognitive/dyon/engineering", signal);
}

export interface DeadModuleRecord {
  rel_file: string;
  module_path: string;
  classification: string;
  confidence: number;
  line_count: number;
  reason: string;
}

export interface DeadCodeResponse {
  runtime?: string;
  scan_count?: number;
  dead_module_count?: number;
  by_classification?: Record<string, number>;
  dead_modules?: DeadModuleRecord[];
  ts_iso?: string;
}

export function fetchDyonDeadCode(
  signal?: AbortSignal,
): Promise<DeadCodeResponse> {
  return _get<DeadCodeResponse>("/api/cognitive/dyon/dead-code", signal);
}

export interface DriftResponse {
  runtime?: string;
  health_score?: number;
  trend?: string;
  grade?: string;
  spike_detected?: boolean;
  scan_count?: number;
  history_series?: number[];
  ts_iso?: string;
}

export function fetchDyonDrift(
  signal?: AbortSignal,
): Promise<DriftResponse> {
  return _get<DriftResponse>("/api/cognitive/dyon/drift", signal);
}

export interface EvolutionReportResponse {
  report_id?: string;
  health_score?: number;
  grade?: string;
  trend?: string;
  files_scanned?: number;
  critical_count?: number;
  warning_count?: number;
  dead_module_count?: number;
  repo_file_count?: number;
  mutation_queue_depth?: number;
  mutations_approved?: number;
  recommendation?: string;
  ts_iso?: string;
}

export function fetchDyonReport(
  signal?: AbortSignal,
): Promise<EvolutionReportResponse> {
  return _get<EvolutionReportResponse>("/api/cognitive/dyon/report", signal);
}

export interface RepoLayerDistribution {
  [layer: string]: number;
}

export interface RepoInspectorResponse {
  runtime?: string;
  status?: string;
  root?: string;
  file_count?: number;
  python_file_count?: number;
  scan_count?: number;
  layer_distribution?: RepoLayerDistribution;
  edge_count?: number;
  isolated_modules?: number;
  top_connected?: { module_path: string; import_count: number }[];
  ts_iso?: string;
}

export function fetchDyonRepo(
  signal?: AbortSignal,
): Promise<RepoInspectorResponse> {
  return _get<RepoInspectorResponse>("/api/cognitive/dyon/repo", signal);
}

// ---------------------------------------------------------------------------
// Stage 6 — Observatory: telemetry, pipeline, simulation, spine, memory, kernel
// ---------------------------------------------------------------------------

export interface TelemetryComponentStats {
  count?: number;
  throughput_per_min?: number;
  p50_ms?: number;
  p99_ms?: number;
}

export interface TelemetrySummaryResponse {
  indira?: TelemetryComponentStats;
  dyon?: TelemetryComponentStats;
  research?: TelemetryComponentStats;
  long_horizon?: TelemetryComponentStats;
  ts_iso?: string;
}

export function fetchTelemetrySummary(
  signal?: AbortSignal,
): Promise<TelemetrySummaryResponse> {
  return _get<TelemetrySummaryResponse>("/api/cognitive/telemetry/summary", signal);
}

export interface PipelineRecord {
  proposal_id?: string;
  stage?: string;
  mutation_class?: string;
  description?: string;
  ts_ns?: number;
}

export interface PipelineResponse {
  runtime?: string;
  tick_count?: number;
  active_count?: number;
  completed_count?: number;
  stage_counts?: Record<string, number>;
  active?: PipelineRecord[];
  recently_completed?: PipelineRecord[];
  ts_iso?: string;
}

export function fetchEvolutionPipeline(
  signal?: AbortSignal,
): Promise<PipelineResponse> {
  return _get<PipelineResponse>("/api/cognitive/evolution/pipeline", signal);
}

export interface ScoreboardEntry {
  fitness?: number;
  wins?: number;
  losses?: number;
  current_streak?: number;
  promoted?: boolean;
}

export interface SimDominanceResponse {
  runtime?: string;
  tick_count?: number;
  tournament_runs?: number;
  dominance_achieved?: boolean;
  dominant_strategy?: string | null;
  scoreboard?: Record<string, ScoreboardEntry>;
  dominance_threshold?: number;
  dominance_streak_required?: number;
  promoted_count?: number;
  ts_iso?: string;
}

export function fetchSimulationDominance(
  signal?: AbortSignal,
): Promise<SimDominanceResponse> {
  return _get<SimDominanceResponse>("/api/cognitive/simulation/dominance", signal);
}

export interface SpineSnapshotResponse {
  spine?: string;
  active?: boolean;
  tick_seq?: number;
  phase_errors?: Record<string, number>;
  cadence?: Record<string, number>;
  subsystems?: Record<string, unknown>;
  ts_iso?: string;
}

export function fetchCognitiveSpine(
  signal?: AbortSignal,
): Promise<SpineSnapshotResponse> {
  return _get<SpineSnapshotResponse>("/api/cognitive/spine", signal);
}

export interface ModeTransitionRecord {
  from_mode?: string;
  to_mode?: string;
  reason?: string;
  ts_ns?: number;
}

export interface GovernanceStoreResponse {
  mode_transitions?: ModeTransitionRecord[];
  violations?: unknown[];
  operator_actions?: unknown[];
  snapshot?: Record<string, unknown>;
  ts_iso?: string;
}

export function fetchGovernanceStore(
  signal?: AbortSignal,
): Promise<GovernanceStoreResponse> {
  return _get<GovernanceStoreResponse>("/api/memory/stores/governance", signal);
}

export interface MemoryLayerSnapshot {
  layer?: string;
  timeline_count?: number;
  index_size?: number;
  stores?: Record<string, number>;
  ts_iso?: string;
}

export function fetchMemorySnapshot(
  signal?: AbortSignal,
): Promise<MemoryLayerSnapshot> {
  return _get<MemoryLayerSnapshot>("/api/memory/snapshot", signal);
}

export interface KernelComponent {
  active?: boolean;
  type?: string;
}

export interface KernelStatusResponse {
  kernel?: string;
  active?: boolean;
  tick_seq?: number;
  components?: Record<string, KernelComponent>;
  ts_iso?: string;
}

export function fetchKernelStatus(
  signal?: AbortSignal,
): Promise<KernelStatusResponse> {
  return _get<KernelStatusResponse>("/api/runtime/cognitive/kernel", signal);
}
