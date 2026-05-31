import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Archive,
  CheckCircle,
  XCircle,
  Download,
  RefreshCw,
  Filter,
} from "lucide-react";

import {
  fetchLedgerTail,
  verifyLedgerChain,
  exportLedger,
  replayLedger,
  type LedgerStream,
  type LedgerEvent,
  type LedgerChainStatus,
} from "@/api/signals";

// ============================================================
// CHAIN STATUS INDICATOR
// ============================================================

function ChainStatusIndicator({ status }: { status: LedgerChainStatus }) {
  return (
    <div
      className={`flex items-center gap-3 rounded border px-4 py-2 ${
        status.ok
          ? "border-ok/40 bg-ok/10"
          : "border-danger/40 bg-danger/10"
      }`}
    >
      {status.ok ? (
        <CheckCircle className="h-5 w-5 text-ok" />
      ) : (
        <XCircle className="h-5 w-5 text-danger" />
      )}
      <div>
        <div className={`text-sm font-medium ${status.ok ? "text-ok" : "text-danger"}`}>
          Chain Status: {status.ok ? "OK" : "BROKEN"}
        </div>
        <div className="text-xs text-text-secondary">
          {status.ok
            ? `Hash verified to seq ${status.verified_to_seq.toLocaleString()}`
            : `Break at seq ${status.break_at_seq?.toLocaleString()} - ${status.break_reason}`}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// STREAM FILTER BAR
// ============================================================

const ALL_STREAMS: LedgerStream[] = ["MARKET", "SYSTEM", "GOVERNANCE", "HAZARD", "SECURITY"];

function StreamFilterBar({
  selectedStreams,
  onToggle,
}: {
  selectedStreams: LedgerStream[];
  onToggle: (stream: LedgerStream) => void;
}) {
  return (
    <div className="rounded border border-border bg-surface p-3">
      <div className="mb-2 flex items-center gap-2 text-xs text-text-secondary">
        <Filter className="h-3.5 w-3.5" />
        Stream Filter
      </div>
      <div className="flex flex-wrap gap-2">
        {ALL_STREAMS.map((stream) => {
          const isSelected = selectedStreams.includes(stream);
          return (
            <button
              key={stream}
              type="button"
              onClick={() => onToggle(stream)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                isSelected
                  ? "bg-accent text-bg"
                  : "border border-border bg-bg text-text-secondary hover:border-accent"
              }`}
            >
              {stream}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// ACTION BAR
// ============================================================

function ActionsBar({
  onVerify,
  onExport,
  onReplay,
  verifying,
  exporting,
  selectedStreams,
}: {
  onVerify: () => void;
  onExport: () => void;
  onReplay: (fromSeq: number) => void;
  verifying: boolean;
  exporting: boolean;
  selectedStreams: LedgerStream[];
}) {
  const [replaySeq, setReplaySeq] = useState("");

  return (
    <div className="flex flex-wrap items-center gap-3 rounded border border-border bg-surface p-3">
      <span className="text-xs text-text-secondary">Actions:</span>

      <button
        type="button"
        onClick={onVerify}
        disabled={verifying}
        className="flex items-center gap-1.5 rounded border border-ok/40 bg-ok/10 px-3 py-1.5 text-xs font-medium text-ok transition-colors hover:bg-ok/20 disabled:opacity-50"
      >
        <CheckCircle className="h-3.5 w-3.5" />
        {verifying ? "Verifying..." : "Verify Chain"}
      </button>

      <button
        type="button"
        onClick={onExport}
        disabled={exporting}
        className="flex items-center gap-1.5 rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
      >
        <Download className="h-3.5 w-3.5" />
        {exporting ? "Exporting..." : "Export Last 1000 JSONL"}
      </button>

      <div className="flex items-center gap-2">
        <input
          type="number"
          value={replaySeq}
          onChange={(e) => setReplaySeq(e.target.value)}
          placeholder="seq"
          className="w-24 rounded border border-border bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          onClick={() => {
            const seq = parseInt(replaySeq, 10);
            if (!isNaN(seq) && seq > 0) {
              onReplay(seq);
            }
          }}
          disabled={!replaySeq}
          className="flex items-center gap-1.5 rounded border border-info/40 bg-info/10 px-3 py-1.5 text-xs font-medium text-info transition-colors hover:bg-info/20 disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Replay from N
        </button>
      </div>
    </div>
  );
}

// ============================================================
// LEDGER EVENT TABLE
// ============================================================

const STREAM_COLORS: Record<LedgerStream, string> = {
  MARKET: "text-ok",
  SYSTEM: "text-info",
  GOVERNANCE: "text-accent",
  HAZARD: "text-warn",
  SECURITY: "text-danger",
};

function LedgerEventTable({ events }: { events: LedgerEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="rounded border border-border bg-surface p-4 text-center text-sm text-text-secondary">
        No events found for selected streams
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-border bg-surface">
      <div className="max-h-[500px] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-border text-left text-text-secondary">
              <th className="px-3 py-2">seq</th>
              <th className="px-3 py-2">ts</th>
              <th className="px-3 py-2">stream</th>
              <th className="px-3 py-2">sub_type</th>
              <th className="px-3 py-2">hash_prefix</th>
              <th className="px-3 py-2">payload</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr
                key={`${event.stream}-${event.seq}`}
                className="border-b border-border/50 hover:bg-bg"
              >
                <td className="px-3 py-2 font-mono text-text-secondary">
                  {event.seq.toLocaleString()}
                </td>
                <td className="px-3 py-2 font-mono text-text-secondary">
                  {new Date(event.timestamp_utc).toLocaleTimeString()}
                </td>
                <td className={`px-3 py-2 font-mono font-medium ${STREAM_COLORS[event.stream]}`}>
                  {event.stream}
                </td>
                <td className="px-3 py-2 font-mono">{event.sub_type}</td>
                <td className="px-3 py-2 font-mono text-text-secondary">
                  {event.hash_prefix}...
                </td>
                <td className="max-w-xs truncate px-3 py-2 font-mono text-[10px] text-text-secondary">
                  {event.payload_preview}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// LEDGER PAGE
// ============================================================

export function LedgerPage() {
  const [selectedStreams, setSelectedStreams] = useState<LedgerStream[]>(ALL_STREAMS);

  const {
    data: ledgerData,
    isPending,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["ledger-tail", selectedStreams],
    queryFn: ({ signal }) =>
      fetchLedgerTail(selectedStreams.length === ALL_STREAMS.length ? undefined : selectedStreams, 100, signal),
    refetchInterval: 3_000,
  });

  const verifyMutation = useMutation({
    mutationFn: verifyLedgerChain,
    onSuccess: () => {
      refetch();
    },
  });

  const exportMutation = useMutation({
    mutationFn: async () => {
      const blob = await exportLedger(
        selectedStreams.length === ALL_STREAMS.length ? undefined : selectedStreams,
        1000
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ledger-export-${Date.now()}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  const replayMutation = useMutation({
    mutationFn: (fromSeq: number) => replayLedger(fromSeq),
    onSuccess: (data) => {
      alert(
        `Replay complete: ${data.events_replayed} events replayed. Rebuilt hash: ${data.rebuilt_hash.slice(0, 8)}...`
      );
    },
  });

  const toggleStream = (stream: LedgerStream) => {
    setSelectedStreams((prev) =>
      prev.includes(stream)
        ? prev.filter((s) => s !== stream)
        : [...prev, stream]
    );
  };

  return (
    <section className="flex h-full flex-col">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Archive className="h-5 w-5 text-accent" />
            Event-Sourced Ledger{" "}
            <span className="ml-2 rounded border border-border bg-bg px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-text-secondary">
              LIVE
            </span>
          </h1>
          <p className="mt-1 text-xs text-text-secondary">
            Immutable, hash-chained, replayable event log. All actions are
            event-sourced with cryptographic verification.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded border border-border bg-surface px-3 py-1.5 text-xs hover:border-accent disabled:opacity-50"
        >
          {isFetching ? "refreshing..." : "refresh"}
        </button>
      </header>

      {isPending && <p className="text-sm text-text-secondary">Loading...</p>}

      {isError && (
        <div className="rounded border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {(error as Error).message}
        </div>
      )}

      {ledgerData && (
        <div className="space-y-4 overflow-auto pb-6">
          <ChainStatusIndicator status={ledgerData.chain_status} />

          <StreamFilterBar
            selectedStreams={selectedStreams}
            onToggle={toggleStream}
          />

          <ActionsBar
            onVerify={() => verifyMutation.mutate()}
            onExport={() => exportMutation.mutate()}
            onReplay={(seq) => replayMutation.mutate(seq)}
            verifying={verifyMutation.isPending}
            exporting={exportMutation.isPending}
            selectedStreams={selectedStreams}
          />

          <div>
            <h2 className="mb-2 text-sm font-medium text-text-secondary">
              Event Log (hash chained, immutable)
            </h2>
            <LedgerEventTable events={ledgerData.events} />
          </div>
        </div>
      )}
    </section>
  );
}
