import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Shield,
  AlertTriangle,
  Power,
  Lock,
  Unlock,
  Clock,
  ArrowRight,
} from "lucide-react";

import {
  fetchSecurityEvents,
  fetchModeTimeline,
  fetchConstraintSet,
  armKillSwitch,
  disarmKillSwitch,
  fireKillSwitch,
  type SecurityEvents,
  type ModeTransition,
  type ExecutionConstraintSet,
  type KillSwitchState,
  type SystemMode,
} from "@/api/signals";

// ============================================================
// KILL SWITCH CONTROL
// ============================================================

const KILL_SWITCH_COLORS: Record<KillSwitchState, string> = {
  ARMED: "border-warn/40 bg-warn/10",
  DISARMED: "border-ok/40 bg-ok/10",
  FIRED: "border-danger/40 bg-danger/10",
};

const KILL_SWITCH_TEXT_COLORS: Record<KillSwitchState, string> = {
  ARMED: "text-warn",
  DISARMED: "text-ok",
  FIRED: "text-danger",
};

function KillSwitchControl({ state }: { state: KillSwitchState }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [fireReason, setFireReason] = useState("");
  const queryClient = useQueryClient();

  const armMutation = useMutation({
    mutationFn: armKillSwitch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-events"] });
    },
  });

  const disarmMutation = useMutation({
    mutationFn: disarmKillSwitch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-events"] });
    },
  });

  const fireMutation = useMutation({
    mutationFn: (reason: string) => fireKillSwitch(reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security-events"] });
      setShowConfirm(false);
      setFireReason("");
    },
  });

  return (
    <div className={`rounded border p-4 ${KILL_SWITCH_COLORS[state]}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Power className={`h-6 w-6 ${KILL_SWITCH_TEXT_COLORS[state]}`} />
          <div>
            <div className="text-sm font-semibold">Kill Switch</div>
            <div className={`text-lg font-bold ${KILL_SWITCH_TEXT_COLORS[state]}`}>
              {state}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {state === "DISARMED" && (
            <button
              type="button"
              onClick={() => armMutation.mutate()}
              disabled={armMutation.isPending}
              className="flex items-center gap-1.5 rounded border border-warn/40 bg-warn/10 px-3 py-1.5 text-xs font-medium text-warn hover:bg-warn/20 disabled:opacity-50"
            >
              <Lock className="h-3.5 w-3.5" />
              {armMutation.isPending ? "Arming..." : "Arm"}
            </button>
          )}

          {state === "ARMED" && (
            <>
              <button
                type="button"
                onClick={() => disarmMutation.mutate()}
                disabled={disarmMutation.isPending}
                className="flex items-center gap-1.5 rounded border border-ok/40 bg-ok/10 px-3 py-1.5 text-xs font-medium text-ok hover:bg-ok/20 disabled:opacity-50"
              >
                <Unlock className="h-3.5 w-3.5" />
                {disarmMutation.isPending ? "Disarming..." : "Disarm"}
              </button>
              <button
                type="button"
                onClick={() => setShowConfirm(true)}
                className="flex items-center gap-1.5 rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/20"
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                FIRE
              </button>
            </>
          )}

          {state === "FIRED" && (
            <span className="text-xs text-danger">
              System halted. Manual intervention required.
            </span>
          )}
        </div>
      </div>

      {showConfirm && (
        <div className="mt-4 rounded border border-danger/40 bg-danger/5 p-3">
          <div className="mb-2 text-sm font-medium text-danger">
            Confirm Kill Switch Activation
          </div>
          <p className="mb-3 text-xs text-text-secondary">
            This will immediately halt all trading activity. This action is
            logged and requires a reason.
          </p>
          <input
            type="text"
            value={fireReason}
            onChange={(e) => setFireReason(e.target.value)}
            placeholder="Reason for firing kill switch"
            className="mb-3 w-full rounded border border-border bg-bg px-3 py-2 text-sm focus:border-danger focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowConfirm(false)}
              className="flex-1 rounded border border-border py-2 text-sm hover:bg-bg"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => fireMutation.mutate(fireReason)}
              disabled={!fireReason.trim() || fireMutation.isPending}
              className="flex-1 rounded bg-danger py-2 text-sm font-medium text-bg hover:bg-danger/90 disabled:opacity-50"
            >
              {fireMutation.isPending ? "Firing..." : "CONFIRM FIRE"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// CONSTRAINT SET PANEL
// ============================================================

function ConstraintSetPanel({ constraints }: { constraints: ExecutionConstraintSet }) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold">
        Current EXECUTION_CONSTRAINT_SET
      </h3>

      <div className="space-y-2">
        <div className="flex items-center justify-between rounded bg-bg px-3 py-2">
          <span className="text-xs text-text-secondary">max_drawdown</span>
          <span className="font-mono text-sm font-medium text-danger">
            {constraints.max_drawdown_percent}%{" "}
            <span className="text-[10px] text-text-secondary">(hard stop)</span>
          </span>
        </div>

        <div className="flex items-center justify-between rounded bg-bg px-3 py-2">
          <span className="text-xs text-text-secondary">max_loss_per_trade</span>
          <span className="font-mono text-sm font-medium text-warn">
            {constraints.max_loss_per_trade_percent}%
          </span>
        </div>

        <div className="flex items-center justify-between rounded bg-bg px-3 py-2">
          <span className="text-xs text-text-secondary">fail_closed</span>
          <span
            className={`font-mono text-sm font-medium ${
              constraints.fail_closed ? "text-ok" : "text-danger"
            }`}
          >
            {constraints.fail_closed ? "true" : "false"}
          </span>
        </div>

        <div className="flex items-center justify-between rounded bg-bg px-3 py-2">
          <span className="text-xs text-text-secondary">trading_allowed</span>
          <span
            className={`font-mono text-sm font-medium ${
              constraints.trading_allowed ? "text-ok" : "text-danger"
            }`}
          >
            {constraints.trading_allowed ? "true" : "false"}
          </span>
        </div>

        <div className="mt-2 border-t border-border pt-2 text-[10px] text-text-secondary">
          last_updated:{" "}
          <span className="font-mono">{constraints.last_updated_utc}</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// AUTHORITY VIOLATIONS PANEL
// ============================================================

function AuthorityViolationsPanel({ events }: { events: SecurityEvents }) {
  return (
    <div className="rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Authority Violations (core.authority.AuthorityViolation)
        </h3>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            events.violation_count_24h > 0
              ? "bg-danger/20 text-danger"
              : "bg-ok/20 text-ok"
          }`}
        >
          {events.violation_count_24h} (last 24h)
        </span>
      </div>

      {events.violations_24h.length === 0 ? (
        <p className="text-sm text-text-secondary">
          No authority violations in the last 24 hours
        </p>
      ) : (
        <ul className="space-y-2">
          {events.violations_24h.map((violation) => (
            <li
              key={violation.id}
              className="rounded border border-danger/30 bg-danger/5 px-3 py-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-text-secondary">
                  {new Date(violation.timestamp_utc).toLocaleTimeString()}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    violation.blocked ? "bg-ok/20 text-ok" : "bg-danger/20 text-danger"
                  }`}
                >
                  {violation.blocked ? "BLOCKED" : "ALLOWED"}
                </span>
              </div>
              <div className="mt-1 text-sm">
                <span className="font-medium text-danger">
                  {violation.violator_domain}
                </span>{" "}
                attempted{" "}
                <span className="font-mono text-text-primary">
                  {violation.attempted_action}
                </span>
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {violation.reason}
              </div>
              <div className="mt-1 font-mono text-[10px] text-text-secondary">
                ledger_seq: {violation.ledger_seq}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ============================================================
// MODE TIMELINE
// ============================================================

const MODE_COLORS: Record<SystemMode, string> = {
  NORMAL: "bg-ok text-bg",
  SAFE: "bg-warn text-bg",
  DEGRADED: "bg-danger/80 text-bg",
  HALTED: "bg-danger text-bg",
};

function ModeTimeline({ transitions }: { transitions: ModeTransition[] }) {
  if (transitions.length === 0) {
    return (
      <div className="rounded border border-border bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold">Mode Transition Timeline</h3>
        <p className="text-sm text-text-secondary">No mode transitions recorded</p>
      </div>
    );
  }

  return (
    <div className="rounded border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold">Mode Transition Timeline</h3>

      <div className="space-y-3">
        {transitions.map((transition, idx) => (
          <div key={transition.id} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-[10px] font-bold ${MODE_COLORS[transition.from_mode]}`}
              >
                {transition.from_mode.slice(0, 1)}
              </div>
              {idx < transitions.length - 1 && (
                <div className="my-1 h-6 w-0.5 bg-border" />
              )}
            </div>

            <div className="flex-1 pt-1">
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${MODE_COLORS[transition.from_mode]}`}>
                  {transition.from_mode}
                </span>
                <ArrowRight className="h-3 w-3 text-text-secondary" />
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${MODE_COLORS[transition.to_mode]}`}>
                  {transition.to_mode}
                </span>
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {transition.reason}
              </div>
              <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-text-secondary">
                <Clock className="h-3 w-3" />
                {new Date(transition.timestamp_utc).toLocaleString()}
                <span>|</span>
                <span>by: {transition.triggered_by}</span>
                <span>|</span>
                <span>seq: {transition.ledger_seq}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 border-t border-border pt-3 text-[10px] text-text-secondary">
        Legend: NORMAL → SAFE → DEGRADED → HALTED
      </div>
    </div>
  );
}

// ============================================================
// SECURITY PAGE
// ============================================================

export function SecurityPage() {
  const {
    data: securityEvents,
    isPending: securityPending,
    isError: securityError,
    error: securityErr,
    refetch: refetchSecurity,
    isFetching: securityFetching,
  } = useQuery({
    queryKey: ["security-events"],
    queryFn: ({ signal }) => fetchSecurityEvents(signal),
    refetchInterval: 3_000,
  });

  const { data: modeTimeline } = useQuery({
    queryKey: ["mode-timeline"],
    queryFn: ({ signal }) => fetchModeTimeline(signal),
    refetchInterval: 5_000,
  });

  const { data: constraints } = useQuery({
    queryKey: ["constraint-set"],
    queryFn: ({ signal }) => fetchConstraintSet(signal),
    refetchInterval: 10_000,
  });

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Shield className="h-5 w-5 text-accent" />
            GOVERNANCE Security & Authority{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-text-secondary">
              LIVE
            </span>
          </h1>
          <p className="mt-1 text-xs text-text-secondary">
            Kill switch control, authority violations, constraint set, and mode
            transitions. GOVERNANCE domain - final decision authority.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetchSecurity()}
          disabled={securityFetching}
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {securityFetching ? "refreshing..." : "refresh"}
        </button>
      </header>

      {securityPending && <p className="text-sm text-text-secondary">Loading...</p>}

      {securityError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(securityErr as Error).message}
        </div>
      )}

      {securityEvents && (
        <div className="space-y-6 overflow-auto pb-6">
          <KillSwitchControl state={securityEvents.kill_switch_state} />

          {constraints && <ConstraintSetPanel constraints={constraints} />}

          <AuthorityViolationsPanel events={securityEvents} />

          {modeTimeline && <ModeTimeline transitions={modeTimeline} />}
        </div>
      )}
    </section>
  );
}
