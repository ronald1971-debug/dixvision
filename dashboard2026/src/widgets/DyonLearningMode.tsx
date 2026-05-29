import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical, GitMerge, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import {
  fetchDyonProposals,
  fetchDyonTopology,
  type PatchProposalRecord,
  type TopologyViolation,
} from "@/api/cognitive";

/**
 * Dyon Learning Mode panel — surfaces what Dyon is *currently
 * learning to fix*, not just what Dyon is currently saying. Backend
 * is wired through:
 *
 *   - PR #32  hazard sensors HAZ-01..12 + health monitors
 *   - PR #33  sandbox / memory_overflow / anomaly_detector hardening
 *   - PR #65  patch pipeline orchestrator + ledger surface (INV-66)
 *   - PR #114 UpdateValidator + UpdateApplier (closed learning loop)
 *
 * Hazard journal and Patch proposals tabs are live (polling backend).
 * Sandbox runs and Promotions tabs show historical seed data.
 */
type Tab = "hazards" | "patches" | "sandbox" | "promotions";

// ---------------------------------------------------------------------------
// Static seed data — sandbox / promotions (no backend yet)
// ---------------------------------------------------------------------------

interface SandboxRun {
  id: string;
  patch_id: string;
  coverage_delta: number;
  regression: boolean;
  lint_clean: boolean;
  duration_ms: number;
}

interface PromotionRow {
  id: string;
  patch_id: string;
  result: "MERGED" | "REVERTED";
  reason: string;
  ts_iso: string;
}

const SANDBOX: SandboxRun[] = [
  {
    id: "sb-001",
    patch_id: "patch-118",
    coverage_delta: 0.012,
    regression: false,
    lint_clean: true,
    duration_ms: 4_810,
  },
  {
    id: "sb-002",
    patch_id: "patch-119",
    coverage_delta: -0.004,
    regression: false,
    lint_clean: true,
    duration_ms: 6_120,
  },
];

const PROMOTIONS: PromotionRow[] = [
  {
    id: "pr-117",
    patch_id: "patch-117",
    result: "MERGED",
    reason: "all gates passed · operator approved",
    ts_iso: "2026-04-21T18:11Z",
  },
  {
    id: "pr-116",
    patch_id: "patch-116",
    result: "REVERTED",
    reason: "post-merge HAZ-LATENCY-P99 spike",
    ts_iso: "2026-04-21T17:02Z",
  },
];

// ---------------------------------------------------------------------------
// Tab config
// ---------------------------------------------------------------------------

const TABS: {
  id: Tab;
  label: string;
  icon: typeof Wrench;
  hint: string;
  live?: boolean;
}[] = [
  { id: "hazards", label: "Hazard journal", icon: AlertTriangle, hint: "LIVE", live: true },
  { id: "patches", label: "Patch proposals", icon: Wrench, hint: "LIVE", live: true },
  { id: "sandbox", label: "Sandbox runs", icon: FlaskConical, hint: "PR #33" },
  { id: "promotions", label: "Promotions", icon: GitMerge, hint: "PR #114" },
];

// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

export function DyonLearningMode() {
  const [tab, setTab] = useState<Tab>("hazards");

  const topoQuery = useQuery({
    queryKey: ["cognitive", "dyon", "topology"],
    queryFn: ({ signal }) => fetchDyonTopology(signal),
    refetchInterval: 30_000,
  });

  const proposalsQuery = useQuery({
    queryKey: ["cognitive", "dyon", "proposals"],
    queryFn: ({ signal }) => fetchDyonProposals(50, signal),
    refetchInterval: 30_000,
  });

  const body = useMemo(() => {
    switch (tab) {
      case "hazards":
        return (
          <HazardsPanel
            violations={topoQuery.data?.violations ?? []}
            filesScanned={topoQuery.data?.files_scanned}
            clean={topoQuery.data?.clean}
            isLoading={topoQuery.isLoading}
            isError={topoQuery.isError}
          />
        );
      case "patches":
        return (
          <PatchesPanel
            proposals={proposalsQuery.data?.proposals ?? []}
            isLoading={proposalsQuery.isLoading}
            isError={proposalsQuery.isError}
          />
        );
      case "sandbox":
        return <SandboxTable rows={SANDBOX} />;
      case "promotions":
        return <PromotionsTable rows={PROMOTIONS} />;
    }
  }, [tab, topoQuery, proposalsQuery]);

  return (
    <div className="flex h-full flex-col rounded border border-border bg-surface text-sm">
      <header className="flex items-baseline justify-between border-b border-border px-3 py-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Dyon · Learning Mode
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">
            hazard journal · patch proposals · sandbox runs · promotion ledger
            — every merge gated
          </p>
        </div>
        <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 font-mono text-[10px] text-accent">
          DYON-L
        </span>
      </header>
      <nav
        className="flex flex-wrap items-center gap-1 border-b border-border bg-bg/50 px-2 py-1.5"
        role="tablist"
        aria-label="Dyon learning sections"
      >
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wider ${
                active
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border bg-bg text-slate-400 hover:text-slate-200"
              }`}
            >
              <Icon className="h-3 w-3" />
              {t.label}
              {t.live ? (
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" title="live" />
              ) : (
                <span className="text-[9px] text-slate-600">{t.hint}</span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="flex-1 overflow-auto">{body}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hazards panel (live — topology violations)
// ---------------------------------------------------------------------------

function topoSeverityClass(sev: string): string {
  return sev === "CRITICAL" ? "text-rose-500" : "text-amber-400";
}

function HazardsPanel({
  violations,
  filesScanned,
  clean,
  isLoading,
  isError,
}: {
  violations: TopologyViolation[];
  filesScanned?: number;
  clean?: boolean;
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex h-24 items-center justify-center font-mono text-[11px] text-slate-500">
        scanning topology…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex h-24 items-center justify-center font-mono text-[11px] text-rose-400">
        topology scan unavailable
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-3 border-b border-border/40 px-3 py-1.5 text-[10px] text-slate-500">
        {filesScanned !== undefined && <span>{filesScanned} files scanned</span>}
        {clean !== undefined && (
          <span className={clean ? "text-emerald-400" : "text-rose-400"}>
            {clean ? "✓ clean" : `${violations.length} violation${violations.length !== 1 ? "s" : ""}`}
          </span>
        )}
      </div>
      {violations.length === 0 ? (
        <div className="flex h-20 items-center justify-center font-mono text-[11px] text-emerald-400">
          no invariant violations
        </div>
      ) : (
        <table className="w-full table-fixed text-left text-[11px]">
          <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="w-1/6 px-3 py-1.5">Invariant</th>
              <th className="w-1/12 px-3 py-1.5">Sev</th>
              <th className="w-1/5 px-3 py-1.5">Source</th>
              <th className="w-1/5 px-3 py-1.5">Imported</th>
              <th className="w-[3rem] px-3 py-1.5 text-right">Line</th>
              <th className="px-3 py-1.5">Description</th>
            </tr>
          </thead>
          <tbody>
            {violations.map((v, i) => (
              <tr key={`${v.invariant_id}-${i}`} className="border-t border-border/60">
                <td className="px-3 py-1.5 font-mono text-accent">
                  {v.invariant_id}
                </td>
                <td className={`px-3 py-1.5 font-mono uppercase ${topoSeverityClass(v.severity)}`}>
                  {v.severity}
                </td>
                <td className="truncate px-3 py-1.5 font-mono text-slate-300">
                  {v.source_module}
                </td>
                <td className="truncate px-3 py-1.5 font-mono text-slate-400">
                  {v.imported_module}
                </td>
                <td className="px-3 py-1.5 text-right font-mono text-slate-500">
                  {v.line}
                </td>
                <td className="px-3 py-1.5 text-slate-300">{v.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Patches panel (live — DYON proposals)
// ---------------------------------------------------------------------------

function proposalSeverityClass(sev?: string): string {
  if (!sev) return "text-slate-400";
  const u = sev.toUpperCase();
  return u === "CRITICAL"
    ? "text-rose-500"
    : u === "WARNING"
      ? "text-amber-400"
      : "text-slate-400";
}

function PatchesPanel({
  proposals,
  isLoading,
  isError,
}: {
  proposals: PatchProposalRecord[];
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex h-24 items-center justify-center font-mono text-[11px] text-slate-500">
        loading proposals…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex h-24 items-center justify-center font-mono text-[11px] text-rose-400">
        proposals unavailable
      </div>
    );
  }
  if (proposals.length === 0) {
    return (
      <div className="flex h-20 items-center justify-center font-mono text-[11px] text-slate-500">
        no patch proposals queued
      </div>
    );
  }

  return (
    <table className="w-full table-fixed text-left text-[11px]">
      <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
        <tr>
          <th className="w-1/8 px-3 py-1.5">Proposal</th>
          <th className="w-1/8 px-3 py-1.5">Invariant</th>
          <th className="w-1/12 px-3 py-1.5">Sev</th>
          <th className="w-1/5 px-3 py-1.5">Source</th>
          <th className="w-1/4 px-3 py-1.5">Description</th>
          <th className="px-3 py-1.5">Action</th>
        </tr>
      </thead>
      <tbody>
        {proposals.map((p, i) => (
          <tr key={p.proposal_id ?? i} className="border-t border-border/60">
            <td className="truncate px-3 py-1.5 font-mono text-accent">
              {p.proposal_id ? p.proposal_id.slice(0, 12) : "—"}
            </td>
            <td className="truncate px-3 py-1.5 font-mono text-slate-400">
              {p.invariant_id ?? "—"}
            </td>
            <td className={`px-3 py-1.5 font-mono uppercase ${proposalSeverityClass(p.severity)}`}>
              {p.severity ?? "—"}
            </td>
            <td className="truncate px-3 py-1.5 font-mono text-slate-300">
              {p.source_module ?? "—"}
            </td>
            <td className="truncate px-3 py-1.5 text-slate-300">
              {p.description ?? "—"}
            </td>
            <td className="px-3 py-1.5 text-slate-400">
              {p.recommended_action ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Static panels — Sandbox / Promotions
// ---------------------------------------------------------------------------

function SandboxTable({ rows }: { rows: SandboxRun[] }) {
  return (
    <table className="w-full table-fixed text-left text-[11px]">
      <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
        <tr>
          <th className="w-1/6 px-3 py-1.5">Run</th>
          <th className="w-1/6 px-3 py-1.5">Patch</th>
          <th className="w-1/6 px-3 py-1.5 text-right">Δ Coverage</th>
          <th className="w-1/6 px-3 py-1.5">Regression</th>
          <th className="w-1/6 px-3 py-1.5">Lint</th>
          <th className="w-1/6 px-3 py-1.5 text-right">Duration</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-t border-border/60">
            <td className="px-3 py-1.5 font-mono text-accent">{r.id}</td>
            <td className="px-3 py-1.5 font-mono text-slate-400">{r.patch_id}</td>
            <td
              className={`px-3 py-1.5 text-right font-mono ${
                r.coverage_delta >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {(r.coverage_delta * 100).toFixed(2)}%
            </td>
            <td
              className={`px-3 py-1.5 font-mono uppercase ${
                r.regression ? "text-rose-400" : "text-emerald-400"
              }`}
            >
              {r.regression ? "yes" : "no"}
            </td>
            <td
              className={`px-3 py-1.5 font-mono uppercase ${
                r.lint_clean ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {r.lint_clean ? "clean" : "dirty"}
            </td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-400">
              {r.duration_ms.toLocaleString()}ms
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PromotionsTable({ rows }: { rows: PromotionRow[] }) {
  return (
    <table className="w-full table-fixed text-left text-[11px]">
      <thead className="sticky top-0 bg-surface text-[10px] uppercase tracking-wider text-slate-500">
        <tr>
          <th className="w-1/6 px-3 py-1.5">Promotion</th>
          <th className="w-1/6 px-3 py-1.5">Patch</th>
          <th className="w-1/6 px-3 py-1.5">Result</th>
          <th className="w-1/3 px-3 py-1.5">Reason</th>
          <th className="w-1/6 px-3 py-1.5">When</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-t border-border/60">
            <td className="px-3 py-1.5 font-mono text-accent">{r.id}</td>
            <td className="px-3 py-1.5 font-mono text-slate-400">{r.patch_id}</td>
            <td
              className={`px-3 py-1.5 font-mono uppercase ${
                r.result === "MERGED" ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {r.result}
            </td>
            <td className="px-3 py-1.5 text-slate-300">{r.reason}</td>
            <td className="px-3 py-1.5 font-mono text-slate-500">{r.ts_iso}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
