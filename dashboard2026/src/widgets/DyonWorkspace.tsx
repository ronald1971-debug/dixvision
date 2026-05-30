import { useEffect, useRef, useState } from "react";

import {
  Activity,
  BarChart2,
  ChevronDown,
  ChevronRight,
  Code2,
  Cpu,
  FileX,
  GitBranch,
  Network,
  RefreshCw,
  Shield,
  Wrench,
} from "lucide-react";

/**
 * DYON Engineering Workspace (STAGE 3 — DYON ACTIVATION)
 *
 * 8-panel operator workspace for DYON's engineering intelligence:
 *
 *   1. REPO GRAPH         — live repository structure (modules, layers, edges)
 *   2. RUNTIME HEALTH     — architecture health score + drift trend
 *   3. MUTATION QUEUE     — GovernedEvolutionPipeline proposal stages
 *   4. DRIFT MONITOR      — violation trend history + spike detection
 *   5. DEAD MODULE DETECTOR — orphaned/isolated/stub module list
 *   6. GOVERNANCE STREAM  — pending CLASS_B/C operator decisions
 *   7. SANDBOX STREAM     — patch simulation outcomes (APPROVED/REJECTED/DEFERRED)
 *   8. PATCH VALIDATION   — recent patch proposals with simulation confidence
 *
 * Data source: GET /api/cognitive/dyon/workspace (polls every 10s)
 * Falls back to seeded data when backend not available.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DriftPoint { ts_ns: number; health_score: number; scan_index: number }

interface DriftState {
  health_score: number;
  trend: "IMPROVING" | "STABLE" | "DEGRADING";
  grade: "A" | "B" | "C" | "D" | "F";
  spike_detected: boolean;
  new_violations_this_scan: number;
  resolved_violations_this_scan: number;
  scan_count: number;
}

interface DeadModule { rel_file: string; module_path: string; classification: string; confidence: number; line_count: number; reason: string }
interface PipelineProposal { proposal_id: string; description: string; source_module: string; mutation_class: string; stage: string; ts_ns_created: number }
interface PatchProposal { proposal_id: string; description: string; source_module: string; severity: string; recommended_action: string }
interface ViolationRecord { violation_key: string; count: number; invariant_id: string; last_severity: string }

interface WorkspaceData {
  activated?: boolean;
  tick_count?: number;
  dyon_core?: {
    scan_count: number;
    tick_count: number;
    latest_scan: { files_scanned: number; violation_count: number; clean: boolean; scan_duration_ms: number } | null;
    recent_proposals: PatchProposal[];
  };
  architecture_drift?: {
    current: DriftState;
    history_series: DriftPoint[];
  };
  repository?: {
    total_files: number;
    total_lines: number;
    layer_distribution: Record<string, number>;
    edge_count: number;
    isolated_module_count: number;
    top_connected_modules: string[];
    scan_duration_ms: number;
  };
  dead_code?: {
    dead_module_count: number;
    by_classification: Record<string, number>;
    dead_modules: DeadModule[];
  };
  mutation_queue?: {
    total_proposals: number;
    stage_counts: Record<string, number>;
    proposals: PipelineProposal[];
  };
  violation_memory?: {
    total_violation_keys: number;
    persistent_violation_count: number;
    top_persistent: ViolationRecord[];
  };
  simulation?: {
    dominance_achieved: boolean;
    tournament_runs: number;
    dominant_strategy: string;
    scoreboard: Record<string, { best_fitness: number; wins: number; dominant: boolean }>;
  };
  latest_report?: {
    report_id: string;
    health_score: number;
    architecture_grade: string;
    drift_trend: string;
    patches_proposed: number;
    patches_promoted: number;
    top_recommendations: string[];
    status_color: string;
  } | null;
}

// ---------------------------------------------------------------------------
// Seed data (shown before first fetch)
// ---------------------------------------------------------------------------

const SEED_DATA: WorkspaceData = {
  activated: true,
  tick_count: 0,
  dyon_core: {
    scan_count: 0,
    tick_count: 0,
    latest_scan: null,
    recent_proposals: [
      { proposal_id: "dyon_p001", description: "Remove direct import of execution_engine from intelligence_engine.meta — B1 violation", source_module: "intelligence_engine.meta.strategy", severity: "CRITICAL", recommended_action: "Route through core.contracts.signals" },
      { proposal_id: "dyon_p002", description: "INV-15: wall-clock import detected in learning_engine.lanes.ewc", source_module: "learning_engine.lanes.ewc", severity: "WARNING", recommended_action: "Inject ts_ns via parameter instead of time.time()" },
    ],
  },
  architecture_drift: {
    current: { health_score: 82, trend: "IMPROVING", grade: "B", spike_detected: false, new_violations_this_scan: 0, resolved_violations_this_scan: 2, scan_count: 0 },
    history_series: [
      { ts_ns: 0, health_score: 65, scan_index: 1 },
      { ts_ns: 1, health_score: 68, scan_index: 2 },
      { ts_ns: 2, health_score: 72, scan_index: 3 },
      { ts_ns: 3, health_score: 78, scan_index: 4 },
      { ts_ns: 4, health_score: 82, scan_index: 5 },
    ],
  },
  repository: {
    total_files: 0,
    total_lines: 0,
    layer_distribution: { L0: 12, L1: 18, L2: 9, L3: 34, L4: 22, L5: 8, L6: 11, L7: 28, L8: 7, UI: 31, SVC: 14, "?": 6 },
    edge_count: 0,
    isolated_module_count: 0,
    top_connected_modules: ["state.event_bus", "core.contracts", "runtime.service_wiring"],
    scan_duration_ms: 0,
  },
  dead_code: {
    dead_module_count: 0,
    by_classification: { STUB: 0, ORPHANED: 0, ISOLATED: 0 },
    dead_modules: [],
  },
  mutation_queue: {
    total_proposals: 0,
    stage_counts: { PROPOSED: 2, SANDBOX: 1, BENCHMARK: 0, GOV_REVIEW: 1, PROMOTED: 3, MONITORING: 1, AUDITED: 5, REJECTED: 0, ROLLED_BACK: 0 },
    proposals: [],
  },
  violation_memory: {
    total_violation_keys: 0,
    persistent_violation_count: 0,
    top_persistent: [],
  },
  simulation: {
    dominance_achieved: false,
    tournament_runs: 0,
    dominant_strategy: "",
    scoreboard: {},
  },
  latest_report: {
    report_id: "initialising",
    health_score: 82,
    architecture_grade: "B",
    drift_trend: "IMPROVING",
    patches_proposed: 0,
    patches_promoted: 0,
    top_recommendations: ["Architecture initialising — first evolution report generating"],
    status_color: "teal",
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function gradeColor(grade: string): string {
  return { A: "text-emerald-400", B: "text-teal-400", C: "text-amber-400", D: "text-orange-400", F: "text-rose-500" }[grade] ?? "text-slate-400";
}

function healthBar(score: number): string {
  if (score >= 90) return "bg-emerald-500";
  if (score >= 75) return "bg-teal-500";
  if (score >= 55) return "bg-amber-500";
  if (score >= 35) return "bg-orange-500";
  return "bg-rose-500";
}

function trendIcon(trend: string): string {
  return { IMPROVING: "↑", STABLE: "→", DEGRADING: "↓" }[trend] ?? "?";
}

function trendColor(trend: string): string {
  return { IMPROVING: "text-emerald-400", STABLE: "text-slate-400", DEGRADING: "text-rose-400" }[trend] ?? "text-slate-400";
}

function sevColor(sev: string): string {
  return { CRITICAL: "text-rose-500", ERROR: "text-rose-400", WARNING: "text-amber-400", INFO: "text-slate-500" }[sev] ?? "text-slate-500";
}

function stageColor(stage: string): string {
  return { PROPOSED: "text-slate-400", SANDBOX: "text-sky-400", BENCHMARK: "text-violet-400", GOV_REVIEW: "text-amber-400", PROMOTED: "text-emerald-400", MONITORING: "text-teal-400", AUDITED: "text-slate-500", REJECTED: "text-rose-400", ROLLED_BACK: "text-orange-400" }[stage] ?? "text-slate-500";
}

function classColor(cls: string): string {
  return { ORPHANED: "text-rose-400", ISOLATED: "text-orange-400", STUB: "text-amber-400", EMPTY: "text-slate-500" }[cls] ?? "text-slate-500";
}

function fmtMs(n: number | undefined): string {
  if (!n) return "—";
  return n < 1000 ? `${n.toFixed(0)}ms` : `${(n / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Panel components
// ---------------------------------------------------------------------------

function PanelHeader({ icon: Icon, title, subtitle, badge }: {
  icon: typeof Cpu; title: string; subtitle?: string; badge?: string;
}) {
  return (
    <div className="flex items-start justify-between border-b border-border px-3 py-2">
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-teal-400 flex-shrink-0" />
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">{title}</h4>
          {subtitle && <p className="text-[10px] text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {badge && (
        <span className="rounded border border-teal-500/40 bg-teal-500/10 px-1.5 py-0.5 font-mono text-[10px] text-teal-300">
          {badge}
        </span>
      )}
    </div>
  );
}

// Panel 1: Repository Graph
function RepoGraphPanel({ data }: { data: WorkspaceData["repository"] }) {
  if (!data) return null;
  const layers = Object.entries(data.layer_distribution).sort((a, b) => a[0].localeCompare(b[0]));
  const maxCount = Math.max(...layers.map(([, c]) => c), 1);
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={Network} title="Repository Graph" subtitle={`${data.total_files} modules · ${data.edge_count} import edges`} />
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {/* Layer distribution bars */}
        <p className="text-[10px] text-slate-500 uppercase tracking-wider">Layer Distribution</p>
        <div className="space-y-1">
          {layers.map(([layer, count]) => (
            <div key={layer} className="flex items-center gap-2">
              <span className="w-7 text-right font-mono text-[10px] text-slate-500">{layer}</span>
              <div className="flex-1 rounded-full bg-bg/60 h-2 overflow-hidden">
                <div
                  className="h-full rounded-full bg-teal-500/60"
                  style={{ width: `${(count / maxCount) * 100}%` }}
                />
              </div>
              <span className="w-6 text-right font-mono text-[10px] text-slate-400">{count}</span>
            </div>
          ))}
        </div>
        {data.isolated_module_count > 0 && (
          <p className="text-[10px] text-amber-400 mt-2">
            ⚠ {data.isolated_module_count} isolated module(s) detected
          </p>
        )}
        {data.top_connected_modules.length > 0 && (
          <>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-3">Top Connected</p>
            <div className="space-y-0.5">
              {data.top_connected_modules.slice(0, 5).map((m) => (
                <p key={m} className="font-mono text-[10px] text-slate-400">{m}</p>
              ))}
            </div>
          </>
        )}
        {data.total_lines > 0 && (
          <p className="text-[10px] text-slate-600 mt-2">{data.total_lines.toLocaleString()} lines · scan {fmtMs(data.scan_duration_ms)}</p>
        )}
      </div>
    </section>
  );
}

// Panel 2: Runtime Health
function RuntimeHealthPanel({ drift, report }: { drift: WorkspaceData["architecture_drift"]; report: WorkspaceData["latest_report"] }) {
  if (!drift) return null;
  const { current, history_series } = drift;
  const trendArrow = trendIcon(current.trend);
  const trendCls = trendColor(current.trend);
  const gradeCls = gradeColor(current.grade);
  const barCls = healthBar(current.health_score);

  // Sparkline from history
  const series = history_series.slice(-20);
  const minH = Math.min(...series.map(p => p.health_score), 0);
  const maxH = Math.max(...series.map(p => p.health_score), 100);
  const range = maxH - minH || 1;

  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={Activity} title="Runtime Health" subtitle="architecture health · drift · grade" />
      <div className="flex-1 overflow-auto p-3 space-y-3">
        {/* Big score */}
        <div className="flex items-end gap-2">
          <span className={`text-3xl font-bold font-mono ${gradeCls}`}>{current.health_score.toFixed(0)}</span>
          <span className="text-slate-500 text-sm">/100</span>
          <span className={`ml-auto text-2xl font-bold font-mono ${gradeCls}`}>{current.grade}</span>
        </div>
        {/* Health bar */}
        <div className="w-full rounded-full bg-bg/60 h-2 overflow-hidden">
          <div className={`h-full rounded-full ${barCls}`} style={{ width: `${current.health_score}%`, transition: "width 0.5s ease" }} />
        </div>
        {/* Trend + spike */}
        <div className="flex items-center gap-3">
          <span className={`text-sm font-mono ${trendCls}`}>{trendArrow} {current.trend}</span>
          {current.spike_detected && (
            <span className="rounded border border-rose-500/40 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10px] text-rose-400">
              ⚠ SPIKE
            </span>
          )}
        </div>
        {/* Stats */}
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded bg-bg/60 p-2">
            <p className="text-slate-500">Scans</p>
            <p className="font-mono text-slate-300">{current.scan_count}</p>
          </div>
          <div className="rounded bg-bg/60 p-2">
            <p className="text-slate-500">New violations</p>
            <p className={`font-mono ${current.new_violations_this_scan > 0 ? "text-rose-400" : "text-emerald-400"}`}>
              {current.new_violations_this_scan > 0 ? `+${current.new_violations_this_scan}` : "0"}
            </p>
          </div>
          <div className="rounded bg-bg/60 p-2">
            <p className="text-slate-500">Resolved</p>
            <p className="font-mono text-emerald-400">{current.resolved_violations_this_scan}</p>
          </div>
        </div>
        {/* Sparkline */}
        {series.length > 1 && (
          <svg viewBox={`0 0 ${series.length * 8} 30`} className="w-full h-8">
            <polyline
              fill="none"
              stroke="#14b8a6"
              strokeWidth="1.5"
              points={series
                .map((p, i) => `${i * 8 + 4},${30 - ((p.health_score - minH) / range) * 26}`)
                .join(" ")}
            />
          </svg>
        )}
        {/* Top recommendation */}
        {report?.top_recommendations?.[0] && (
          <p className="text-[10px] text-slate-400 leading-snug border-t border-border/50 pt-2">
            <span className="text-teal-400">▸ </span>{report.top_recommendations[0]}
          </p>
        )}
      </div>
    </section>
  );
}

// Panel 3: Mutation Queue
function MutationQueuePanel({ queue }: { queue: WorkspaceData["mutation_queue"] }) {
  if (!queue) return null;
  const stages = Object.entries(queue.stage_counts);
  const total = Object.values(queue.stage_counts).reduce((a, b) => a + b, 0);
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={GitBranch} title="Mutation Queue" subtitle={`${total} total proposals`} />
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {/* Stage distribution */}
        <div className="space-y-1">
          {stages.filter(([, c]) => c > 0).map(([stage, count]) => (
            <div key={stage} className="flex items-center justify-between gap-2">
              <span className={`font-mono text-[10px] ${stageColor(stage)}`}>{stage}</span>
              <span className="font-mono text-[10px] text-slate-400">{count}</span>
            </div>
          ))}
        </div>
        {/* Recent proposals */}
        {queue.proposals.length > 0 && (
          <>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-3 border-t border-border/50 pt-2">Recent</p>
            <div className="space-y-2">
              {queue.proposals.slice(0, 5).map((p) => (
                <div key={p.proposal_id} className="rounded bg-bg/40 px-2 py-1.5">
                  <div className="flex items-center justify-between gap-1">
                    <span className={`font-mono text-[10px] ${stageColor(p.stage)}`}>{p.stage}</span>
                    <span className="font-mono text-[10px] text-slate-600">{p.mutation_class}</span>
                  </div>
                  <p className="text-[10px] text-slate-400 mt-0.5 leading-snug">{p.description.slice(0, 80)}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

// Panel 4: Drift Monitor
function DriftMonitorPanel({ drift }: { drift: WorkspaceData["architecture_drift"] }) {
  if (!drift) return null;
  const series = drift.history_series;
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={BarChart2} title="Drift Monitor" subtitle="violation trend · scan history" />
      <div className="flex-1 overflow-auto p-3 space-y-3">
        {series.length > 0 ? (
          <>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider">Health Score History</p>
            {/* Simple text-based trend bars */}
            <div className="space-y-1">
              {series.slice(-15).map((p, i) => {
                const w = `${p.health_score}%`;
                const cls = healthBar(p.health_score);
                return (
                  <div key={i} className="flex items-center gap-2">
                    <span className="w-4 text-right font-mono text-[9px] text-slate-600">{p.scan_index}</span>
                    <div className="flex-1 rounded-full bg-bg/60 h-1.5 overflow-hidden">
                      <div className={`h-full rounded-full ${cls}`} style={{ width: w }} />
                    </div>
                    <span className="w-8 text-right font-mono text-[9px] text-slate-500">{p.health_score.toFixed(0)}</span>
                  </div>
                );
              })}
            </div>
            <div className="flex items-center gap-3 pt-1 border-t border-border/50">
              <span className={`text-xs font-mono ${trendColor(drift.current.trend)}`}>
                {trendIcon(drift.current.trend)} {drift.current.trend}
              </span>
              {drift.current.spike_detected && (
                <span className="text-[10px] text-rose-400">⚠ Spike this scan</span>
              )}
            </div>
          </>
        ) : (
          <p className="text-[11px] text-slate-500">Waiting for first topology scan…</p>
        )}
      </div>
    </section>
  );
}

// Panel 5: Dead Module Detector
function DeadModulePanel({ data }: { data: WorkspaceData["dead_code"] }) {
  if (!data) return null;
  const [expanded, setExpanded] = useState<string | null>(null);
  const byClass = Object.entries(data.by_classification).filter(([, c]) => c > 0);
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={FileX} title="Dead Modules" subtitle={`${data.dead_module_count} suspect`} />
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {byClass.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {byClass.map(([cls, count]) => (
              <span key={cls} className={`rounded border border-border/40 px-1.5 py-0.5 font-mono text-[10px] ${classColor(cls)}`}>
                {cls} {count}
              </span>
            ))}
          </div>
        )}
        {data.dead_modules.length === 0 && (
          <p className="text-[11px] text-slate-500">No dead modules detected (or scan pending)</p>
        )}
        <div className="space-y-1">
          {data.dead_modules.slice(0, 20).map((dm) => {
            const open = expanded === dm.rel_file;
            return (
              <button
                key={dm.rel_file}
                type="button"
                onClick={() => setExpanded(open ? null : dm.rel_file)}
                className="w-full rounded bg-bg/40 px-2 py-1.5 text-left hover:bg-bg/70"
              >
                <div className="flex items-center justify-between gap-1">
                  <span className={`font-mono text-[10px] ${classColor(dm.classification)}`}>{dm.classification}</span>
                  <span className="font-mono text-[10px] text-slate-600">{(dm.confidence * 100).toFixed(0)}%</span>
                </div>
                <p className="text-[10px] text-slate-400 font-mono mt-0.5 truncate">{dm.rel_file}</p>
                {open && (
                  <p className="mt-1 text-[10px] text-slate-500 leading-snug">{dm.reason}</p>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// Panel 6: Governance Approval Stream
function GovernanceApprovalPanel({ queue }: { queue: WorkspaceData["mutation_queue"] }) {
  const pending = (queue?.proposals ?? []).filter((p) =>
    ["GOV_REVIEW"].includes(p.stage)
  );
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={Shield} title="Governance Stream" subtitle="pending operator decisions" badge={pending.length > 0 ? `${pending.length} PENDING` : undefined} />
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {pending.length === 0 ? (
          <div className="text-[11px] text-slate-500 space-y-1">
            <p className="text-emerald-400">✓ No proposals awaiting operator approval</p>
            <p>CLASS_A mutations are auto-approved.</p>
            <p>CLASS_B/C require your decision here.</p>
          </div>
        ) : (
          pending.slice(0, 10).map((p) => (
            <div key={p.proposal_id} className="rounded border border-amber-500/20 bg-amber-500/5 px-2 py-2 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] text-amber-400">GOV_REVIEW</span>
                <span className="font-mono text-[10px] text-slate-600">{p.mutation_class}</span>
              </div>
              <p className="text-[10px] text-slate-300 leading-snug">{p.description.slice(0, 100)}</p>
              <p className="font-mono text-[10px] text-slate-600">{p.source_module}</p>
            </div>
          ))
        )}
        {/* Stage breakdown for governance context */}
        {queue && (
          <div className="border-t border-border/50 pt-2 space-y-1">
            {["PROPOSED", "SANDBOX", "BENCHMARK", "GOV_REVIEW"].map((s) => {
              const c = queue.stage_counts[s] ?? 0;
              return c > 0 ? (
                <div key={s} className="flex items-center justify-between">
                  <span className={`font-mono text-[10px] ${stageColor(s)}`}>{s}</span>
                  <span className="font-mono text-[10px] text-slate-500">{c}</span>
                </div>
              ) : null;
            })}
          </div>
        )}
      </div>
    </section>
  );
}

// Panel 7: Sandbox Execution Stream
function SandboxStreamPanel({ simulation }: { simulation: WorkspaceData["simulation"] }) {
  if (!simulation) return null;
  const entries = Object.entries(simulation.scoreboard);
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={Code2} title="Sandbox Stream" subtitle="simulation outcomes · tournament results" />
      <div className="flex-1 overflow-auto p-3 space-y-2">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-slate-500">Tournament runs</span>
          <span className="font-mono text-slate-300">{simulation.tournament_runs}</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-slate-500">Dominance achieved</span>
          <span className={`font-mono ${simulation.dominance_achieved ? "text-emerald-400" : "text-slate-500"}`}>
            {simulation.dominance_achieved ? "✓ YES" : "—"}
          </span>
        </div>
        {simulation.dominant_strategy && (
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-500">Dominant strategy</span>
            <span className="font-mono text-teal-400 text-[10px]">{simulation.dominant_strategy.slice(0, 24)}</span>
          </div>
        )}
        {entries.length > 0 && (
          <>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-3 border-t border-border/50 pt-2">Scoreboard</p>
            <div className="space-y-1">
              {entries
                .sort(([, a], [, b]) => b.best_fitness - a.best_fitness)
                .slice(0, 8)
                .map(([sid, rec]) => (
                  <div key={sid} className="flex items-center gap-2">
                    <div className="flex-1 min-w-0">
                      <span className="font-mono text-[10px] text-slate-400 truncate">{sid.slice(0, 20)}</span>
                    </div>
                    <span className={`font-mono text-[10px] ${rec.dominant ? "text-emerald-400" : "text-slate-500"}`}>
                      {rec.best_fitness.toFixed(1)}
                    </span>
                    {rec.dominant && <span className="text-[9px] text-emerald-400">★</span>}
                  </div>
                ))}
            </div>
          </>
        )}
        {entries.length === 0 && simulation.tournament_runs === 0 && (
          <p className="text-[11px] text-slate-500">First tournament pending (every 100 dyon ticks)</p>
        )}
      </div>
    </section>
  );
}

// Panel 8: Patch Validation Stream
function PatchValidationPanel({ proposals }: { proposals: PatchProposal[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section className="flex flex-col rounded border border-border bg-surface h-full">
      <PanelHeader icon={Wrench} title="Patch Validation" subtitle="recent proposals with simulation verdict" />
      <div className="flex-1 overflow-auto divide-y divide-border/40">
        {proposals.length === 0 && (
          <p className="p-3 text-[11px] text-slate-500">No patch proposals yet — waiting for first topology scan</p>
        )}
        {proposals.slice(0, 15).map((p) => {
          const open = expanded === p.proposal_id;
          return (
            <button
              key={p.proposal_id}
              type="button"
              onClick={() => setExpanded(open ? null : p.proposal_id)}
              className="w-full px-3 py-2 text-left hover:bg-bg/60"
            >
              <div className="flex items-start gap-2">
                <Wrench className={`mt-0.5 h-3 w-3 flex-shrink-0 ${sevColor(p.severity)}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className={`font-mono text-[10px] ${sevColor(p.severity)}`}>{p.severity}</span>
                    {open ? <ChevronDown className="h-3 w-3 text-slate-600" /> : <ChevronRight className="h-3 w-3 text-slate-600" />}
                  </div>
                  <p className="mt-0.5 text-[10px] text-slate-300 leading-snug">{p.description.slice(0, 90)}</p>
                  <p className="font-mono text-[9px] text-slate-600 mt-0.5">{p.source_module}</p>
                  {open && (
                    <p className="mt-1.5 rounded bg-bg/60 px-2 py-1 font-mono text-[10px] text-slate-400 leading-relaxed">
                      Action: {p.recommended_action.slice(0, 120)}
                    </p>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main DyonWorkspace
// ---------------------------------------------------------------------------

export function DyonWorkspace() {
  const [data, setData] = useState<WorkspaceData>(SEED_DATA);
  const [loading, setLoading] = useState(false);
  const [lastFetch, setLastFetch] = useState<string>("");
  const [live, setLive] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchWorkspace = async () => {
    setLoading(true);
    try {
      const resp = await fetch("/api/cognitive/dyon/workspace");
      if (resp.ok) {
        const json = await resp.json();
        if (!json.error) {
          setData(json);
          setLive(true);
        }
      }
    } catch {
      setLive(false);
    } finally {
      setLoading(false);
      const now = new Date();
      setLastFetch(
        `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`
      );
    }
  };

  useEffect(() => {
    fetchWorkspace();
    timerRef.current = setInterval(fetchWorkspace, 10_000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const proposals = data.dyon_core?.recent_proposals ?? [];

  return (
    <section className="flex h-full flex-col rounded border border-border bg-surface">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-teal-400" />
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              DYON · Engineering Workspace
            </h3>
            <p className="mt-0.5 text-[10px] text-slate-500">
              repository · health · mutations · drift · dead modules · governance · sandbox · patches
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {loading && <RefreshCw className="h-3 w-3 text-slate-600 animate-spin" />}
          {lastFetch && <span className="font-mono text-[10px] text-slate-600">{lastFetch}</span>}
          <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${live ? "border-teal-500/40 bg-teal-500/10 text-teal-300" : "border-slate-600 bg-bg/40 text-slate-500"}`}>
            {live ? "LIVE" : "SIM"}
          </span>
          {data.architecture_drift && (
            <span className={`rounded border border-border/40 px-1.5 py-0.5 font-mono text-[10px] ${gradeColor(data.architecture_drift.current.grade)}`}>
              {data.architecture_drift.current.grade} {data.architecture_drift.current.health_score.toFixed(0)}/100
            </span>
          )}
        </div>
      </header>

      {/* 8-panel grid: 4 columns × 2 rows */}
      <div className="flex-1 overflow-auto p-3">
        <div className="grid grid-cols-4 gap-3 h-full min-h-0" style={{ gridTemplateRows: "1fr 1fr" }}>
          {/* Row 1 */}
          <RepoGraphPanel data={data.repository} />
          <RuntimeHealthPanel drift={data.architecture_drift} report={data.latest_report} />
          <MutationQueuePanel queue={data.mutation_queue} />
          <DriftMonitorPanel drift={data.architecture_drift} />
          {/* Row 2 */}
          <DeadModulePanel data={data.dead_code} />
          <GovernanceApprovalPanel queue={data.mutation_queue} />
          <SandboxStreamPanel simulation={data.simulation} />
          <PatchValidationPanel proposals={proposals} />
        </div>
      </div>

      {/* Footer status bar */}
      {data.latest_report && (
        <footer className="border-t border-border/50 px-4 py-1.5 flex items-center gap-4">
          <span className="font-mono text-[10px] text-slate-500">
            Report {data.latest_report.report_id}
          </span>
          <span className="text-[10px] text-slate-400">
            {data.latest_report.top_recommendations?.[0]?.slice(0, 80)}
          </span>
          {data.activated && (
            <span className="ml-auto font-mono text-[10px] text-teal-400">DYON ACTIVE</span>
          )}
        </footer>
      )}
    </section>
  );
}
