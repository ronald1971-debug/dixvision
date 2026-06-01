export function KillSwitchPill() {
  return (
    <span className="flex items-center gap-1.5 rounded border border-ok/40 bg-ok/10 px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-ok">
      <span className="h-2 w-2 rounded-full bg-ok animate-pulse" />
      KS: ARMED
    </span>
  );
}
