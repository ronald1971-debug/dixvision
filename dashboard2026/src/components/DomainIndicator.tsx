import { useHashRoute, type Route } from "@/router";

const DOMAIN_MAP: Record<Route, string> = {
  spot: "INDIRA",
  perps: "INDIRA",
  dex: "INDIRA",
  forex: "INDIRA",
  stocks: "INDIRA",
  nft: "INDIRA",
  operator: "SYSTEM",
  credentials: "SYSTEM",
  chat: "SYSTEM",
  indira: "SYSTEM",
  dyon: "SYSTEM",
  observatory: "SYSTEM",
  testing: "SYSTEM",
  onchain: "SYSTEM",
  ai: "SYSTEM",
  orderflow: "INDIRA",
  governance: "GOVERNANCE",
  risk: "GOVERNANCE",
  charting: "INDIRA",
  market: "INDIRA",
  positions: "INDIRA",
  trading: "INDIRA",
  plugins: "SYSTEM",
  syshealth: "DYON",
  alerts: "DYON",
  audit: "LEDGER",
  scout: "DYON",
  strategies: "INDIRA",
  memory: "LEDGER",
  fabric: "LEDGER",
  simulation: "SYSTEM",
  signals: "DYON",
  forms: "INDIRA",
  adapters: "DYON",
  ledger: "LEDGER",
  security: "GOVERNANCE",
  hazards: "DYON",
};

const DOMAIN_CLS: Record<string, string> = {
  INDIRA: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  DYON: "border-blue-400/30 bg-blue-500/10 text-blue-400",
  GOVERNANCE: "border-violet-400/30 bg-violet-500/10 text-violet-400",
  LEDGER: "border-amber-400/30 bg-amber-500/10 text-amber-400",
  SYSTEM: "border-slate-500/30 bg-slate-500/10 text-slate-400",
};

export function DomainIndicator() {
  const route = useHashRoute();
  const domain = DOMAIN_MAP[route] ?? "SYSTEM";
  return (
    <span className={`flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider ${DOMAIN_CLS[domain] ?? DOMAIN_CLS.SYSTEM}`}>
      DOMAIN: {domain}
    </span>
  );
}
