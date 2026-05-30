import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  fetchOperatorSummary,
  fetchTradingAllowed,
  postOperatorKill,
  postTradingAllowed,
} from "@/api/operator";
import { AdapterStatusGrid } from "@/components/AdapterStatusGrid";
import { EngineBucketBadge } from "@/components/EngineBucketBadge";
import { HotkeyConfigurator } from "@/components/HotkeyConfigurator";
import { PopoutButton } from "@/components/PopoutButton";
import { WidgetSlot } from "@/components/WidgetSlot";
import type {
  OperatorActionResponse,
  OperatorStrategyCounts,
} from "@/types/generated/api";

// Mirrors ``StrategyState`` one-for-one. Strategy-level SHADOW was
// demolished by SHADOW-DEMOLITION-02 (PR #216); PAPER at the
// system-mode layer supplies the equivalent observe-only behaviour.
const STRATEGY_LABELS: Array<[keyof OperatorStrategyCounts, string]> = [
  ["proposed", "PROPOSED"],
  ["canary", "CANARY"],
  ["live", "LIVE"],
  ["retired", "RETIRED"],
  ["failed", "FAILED"],
];

export function OperatorPage() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["operator", "summary"],
    queryFn: ({ signal }) => fetchOperatorSummary(signal),
    refetchInterval: 5_000,
  });

  const [killReason, setKillReason] = useState("operator kill");
  const [actionLog, setActionLog] = useState<
    Array<{ ts: string; approved: boolean; summary: string }>
  >([]);

  const killMutation = useMutation({
    mutationFn: () => postOperatorKill({ reason: killReason }),
    onSuccess: (resp: OperatorActionResponse) => {
      setActionLog((rows) => [
        {
          ts: new Date().toLocaleTimeString(),
          approved: resp.approved,
          summary: resp.summary,
        },
        ...rows.slice(0, 9),
      ]);
      queryClient.invalidateQueries({ queryKey: ["operator", "summary"] });
    },
    onError: (err: Error) => {
      setActionLog((rows) => [
        {
          ts: new Date().toLocaleTimeString(),
          approved: false,
          summary: `request failed: ${err.message}`,
        },
        ...rows.slice(0, 9),
      ]);
    },
  });

  return (
    <section className="max-w-6xl mx-auto space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            Operator control plane
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Mode FSM, engine health, strategy counts, and the kill
            switch. Read projection of the Phase 6 widgets, refreshed
            every 5 s.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <PopoutButton route="operator" />
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
            disabled={isFetching}
          >
            {isFetching ? "refreshing…" : "refresh"}
          </button>
        </div>
      </div>

      {isPending && <p className="text-sm text-slate-400">Loading…</p>}

      {isError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          Failed to load operator summary: {(error as Error).message}
        </div>
      )}

      {data && (
        <>
          <WidgetSlot widgetKey="operator:ModeCard">
            <ModeCard data={data.mode} />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:EnginesCard">
            <EnginesCard rows={data.engines} />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:AdapterStatusGrid">
            <AdapterStatusGrid />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:StrategiesCard">
            <StrategiesCard counts={data.strategies} />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:MemecoinCard">
            <MemecoinCard data={data.memecoin} />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:DecisionCountCard">
            <DecisionCountCard count={data.decision_chain_count} />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:TradingGate">
            <TradingGateCard />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:KillCard">
            <KillCard
              reason={killReason}
              onReasonChange={setKillReason}
              onKill={() => killMutation.mutate()}
              isSubmitting={killMutation.isPending}
              log={actionLog}
              isLocked={data.mode.is_locked}
            />
          </WidgetSlot>
          <WidgetSlot widgetKey="operator:HotkeyConfigurator">
            <HotkeyConfigurator />
          </WidgetSlot>
        </>
      )}
    </section>
  );
}

function ModeCard({
  data,
}: {
  data: { current_mode: string; legal_targets: string[]; is_locked: boolean };
}) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Mode FSM <span className="ml-2 text-slate-600">DASH-02</span>
      </h2>
      <div className="grid grid-cols-3 gap-4">
        <Tile label="current mode" value={data.current_mode} />
        <Tile
          label="legal targets"
          value={data.legal_targets.join(", ") || "—"}
        />
        <Tile
          label="locked"
          value={data.is_locked ? "yes" : "no"}
          tone={data.is_locked ? "danger" : "ok"}
        />
      </div>
    </div>
  );
}

function EnginesCard({
  rows,
}: {
  rows: Array<{
    engine_name: string;
    bucket: string;
    detail: string;
    plugin_count: number;
  }>;
}) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Engine status <span className="ml-2 text-slate-600">DASH-EG-01</span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">no engines registered</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">engine</th>
              <th className="px-3 py-2">bucket</th>
              <th className="px-3 py-2">detail</th>
              <th className="px-3 py-2 text-right">plugins</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.engine_name} className="border-t border-border">
                <td className="px-3 py-2 font-mono text-xs">
                  {row.engine_name}
                </td>
                <td className="px-3 py-2">
                  <EngineBucketBadge bucket={row.bucket} />
                </td>
                <td className="px-3 py-2 text-xs text-slate-400">
                  {row.detail || "—"}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {row.plugin_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StrategiesCard({ counts }: { counts: OperatorStrategyCounts }) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Strategy lifecycle{" "}
        <span className="ml-2 text-slate-600">DASH-SLP-01</span>
      </h2>
      <div className="grid grid-cols-6 gap-2 font-mono text-xs">
        {STRATEGY_LABELS.map(([key, label]) => (
          <Tile key={key} label={label.toLowerCase()} value={counts[key]} />
        ))}
      </div>
    </div>
  );
}

function MemecoinCard({
  data,
}: {
  data: { enabled: boolean; killed: boolean; summary: string };
}) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Memecoin subsystem{" "}
        <span className="ml-2 text-slate-600">DASH-MCP-01</span>
      </h2>
      <div className="grid grid-cols-3 gap-4">
        <Tile
          label="enabled"
          value={data.enabled ? "yes" : "no"}
          tone={data.enabled ? "ok" : undefined}
        />
        <Tile
          label="killed"
          value={data.killed ? "yes" : "no"}
          tone={data.killed ? "danger" : undefined}
        />
        <Tile label="summary" value={data.summary || "—"} />
      </div>
      <div className="mt-3 flex items-center justify-between rounded border border-border bg-surface-2 px-3 py-2 text-sm">
        <span className="text-slate-400">
          Full memecoin cockpit lives on the dedicated DEXtools-styled
          dashboard.
        </span>
        <a
          href="/meme/"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded border border-accent px-3 py-1 font-mono text-xs text-accent hover:bg-accent hover:text-surface"
        >
          open /meme/ →
        </a>
      </div>
    </div>
  );
}

function DecisionCountCard({ count }: { count: number }) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Decision trace <span className="ml-2 text-slate-600">DASH-04</span>
      </h2>
      <Tile label="symbols traced" value={count} />
      <p className="mt-2 text-xs text-slate-500">
        Per-event detail rolls up on the legacy <code>/operator</code>{" "}
        page; richer trace view is queued for a follow-up wave-02 PR.
      </p>
    </div>
  );
}

function KillCard({
  reason,
  onReasonChange,
  onKill,
  isSubmitting,
  log,
  isLocked,
}: {
  reason: string;
  onReasonChange: (v: string) => void;
  onKill: () => void;
  isSubmitting: boolean;
  log: Array<{ ts: string; approved: boolean; summary: string }>;
  isLocked: boolean;
}) {
  return (
    <div className="rounded border border-danger/40 bg-danger/5 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-danger">
        Kill switch
      </h2>
      <p className="mb-3 text-xs text-slate-400">
        Submits a <code>REQUEST_KILL</code> through{" "}
        <code>ControlPlaneRouter</code> →{" "}
        <code>OperatorInterfaceBridge</code> (GOV-CP-07). The decision
        Governance returns is logged below verbatim.
        {isLocked && (
          <span className="ml-1 text-warn">
            System is already LOCKED — a fresh kill will likely be a
            no-op.
          </span>
        )}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!isSubmitting) onKill();
        }}
        className="mb-3 flex flex-wrap items-end gap-2"
      >
        <label className="flex flex-col text-xs text-slate-400">
          reason
          <input
            type="text"
            value={reason}
            onChange={(e) => onReasonChange(e.target.value)}
            className="mt-1 w-72 rounded border border-border bg-surface px-2 py-1 font-mono text-xs text-slate-200"
            maxLength={512}
          />
        </label>
        <button
          type="submit"
          disabled={isSubmitting || reason.trim().length === 0}
          className="rounded border border-danger bg-danger/20 px-4 py-1.5 text-xs font-semibold text-danger hover:bg-danger/30 disabled:opacity-50"
        >
          {isSubmitting ? "submitting…" : "KILL"}
        </button>
      </form>

      {log.length === 0 ? (
        <p className="text-xs text-slate-500">no operator actions yet</p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {log.map((row, idx) => (
            <li
              key={idx}
              className={
                row.approved ? "text-ok" : "text-danger"
              }
            >
              [{row.ts}] {row.approved ? "OK" : "DENY"} — {row.summary}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const CONFIRM_PHRASE = "ENABLE LIVE TRADING";

function TradingGateCard() {
  const queryClient = useQueryClient();
  const [confirmText, setConfirmText] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [auditLog, setAuditLog] = useState<
    Array<{ ts: string; enabled: boolean }>
  >([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data, isPending } = useQuery({
    queryKey: ["operator", "trading-allowed"],
    queryFn: ({ signal }) => fetchTradingAllowed(signal),
    refetchInterval: 5_000,
  });

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) => postTradingAllowed(enabled),
    onSuccess: (resp) => {
      setAuditLog((rows) => [
        { ts: new Date().toLocaleTimeString(), enabled: resp.trading_allowed },
        ...rows.slice(0, 9),
      ]);
      setShowConfirm(false);
      setConfirmText("");
      queryClient.invalidateQueries({ queryKey: ["operator", "trading-allowed"] });
    },
  });

  const isLive = data?.trading_allowed ?? false;

  const handleToggle = () => {
    if (isLive) {
      // Turning OFF is always safe — no confirmation required
      toggleMutation.mutate(false);
    } else {
      setShowConfirm(true);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleConfirm = () => {
    if (confirmText.trim().toUpperCase() === CONFIRM_PHRASE) {
      toggleMutation.mutate(true);
    }
  };

  const handleCancel = () => {
    setShowConfirm(false);
    setConfirmText("");
  };

  return (
    <div
      className={`rounded border p-4 transition-colors ${
        isLive
          ? "border-amber-500/60 bg-amber-950/20"
          : "border-emerald-800/40 bg-emerald-950/10"
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Execution gate
        </h2>
        <span
          className={`rounded px-2 py-0.5 text-xs font-bold ${
            isLive
              ? "bg-amber-500/20 text-amber-300"
              : "bg-emerald-900/40 text-emerald-400"
          }`}
        >
          {isPending ? "…" : isLive ? "LIVE TRADING ENABLED" : "PAPER ONLY"}
        </span>
      </div>

      <p className="mb-4 text-xs text-slate-400">
        {isLive
          ? "Live capital deployment is active. Orders sent to real venues and real funds are at risk. Flip this gate off to return to paper-only mode instantly."
          : "System is in paper-only mode. No real capital is deployed. All orders are simulated. Flip this gate to enable live trading — requires typed confirmation."}
      </p>

      {/* Main toggle button */}
      {!showConfirm && (
        <button
          type="button"
          onClick={handleToggle}
          disabled={isPending || toggleMutation.isPending}
          className={`rounded px-4 py-2 text-sm font-semibold transition disabled:opacity-50 ${
            isLive
              ? "bg-emerald-700 text-white hover:bg-emerald-600"
              : "bg-amber-700 text-white hover:bg-amber-600"
          }`}
        >
          {toggleMutation.isPending
            ? "Updating…"
            : isLive
              ? "Disable live trading"
              : "Enable live trading…"}
        </button>
      )}

      {/* Two-step confirmation — only shown when flipping to LIVE */}
      {showConfirm && (
        <div className="rounded border border-amber-600/50 bg-amber-950/30 p-3">
          <p className="mb-2 text-xs font-semibold text-amber-300">
            Type <span className="font-mono">{CONFIRM_PHRASE}</span> to confirm
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleConfirm();
                if (e.key === "Escape") handleCancel();
              }}
              placeholder={CONFIRM_PHRASE}
              className="w-64 rounded border border-amber-700/60 bg-slate-900 px-2 py-1 font-mono text-xs text-amber-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-amber-600"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              onClick={handleConfirm}
              disabled={
                confirmText.trim().toUpperCase() !== CONFIRM_PHRASE ||
                toggleMutation.isPending
              }
              className="rounded bg-amber-600 px-3 py-1 text-xs font-semibold text-white transition hover:bg-amber-500 disabled:opacity-40"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="rounded bg-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:bg-slate-600"
            >
              Cancel
            </button>
          </div>
          {toggleMutation.isError && (
            <p className="mt-2 text-xs text-red-400">
              {(toggleMutation.error as Error).message}
            </p>
          )}
        </div>
      )}

      {/* Audit log */}
      {auditLog.length > 0 && (
        <ul className="mt-3 space-y-0.5 border-t border-slate-700/60 pt-2">
          {auditLog.map((row, i) => (
            <li key={i} className="font-mono text-[10px] text-slate-400">
              [{row.ts}]{" "}
              <span className={row.enabled ? "text-amber-300" : "text-emerald-400"}>
                {row.enabled ? "LIVE TRADING ENABLED" : "PAPER ONLY"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "ok" | "warn" | "danger";
}) {
  const toneClass =
    tone === "ok"
      ? "text-ok"
      : tone === "warn"
        ? "text-warn"
        : tone === "danger"
          ? "text-danger"
          : "text-slate-200";
  return (
    <div className="rounded border border-border bg-bg px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 font-mono text-sm ${toneClass}`}>{value}</div>
    </div>
  );
}
