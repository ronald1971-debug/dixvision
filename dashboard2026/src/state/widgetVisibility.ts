import type { ReactNode } from "react";
import { useMemo, useSyncExternalStore } from "react";

export interface WidgetDef {
  key: string;
  label: string;
}

export interface PageDef {
  id: string;
  label: string;
  group: string;
  widgets: WidgetDef[];
}

export const WIDGET_REGISTRY: PageDef[] = [
  // ── System ────────────────────────────────────────────────────────────────
  {
    id: "operator",
    label: "Operator",
    group: "System",
    widgets: [
      { key: "operator:ModeCard", label: "Mode FSM" },
      { key: "operator:EnginesCard", label: "Engine Status" },
      { key: "operator:AdapterStatusGrid", label: "Adapters" },
      { key: "operator:StrategiesCard", label: "Strategies" },
      { key: "operator:MemecoinCard", label: "Memecoin" },
      { key: "operator:DecisionCountCard", label: "Decision Count" },
      { key: "operator:TradingGate", label: "Execution Gate" },
      { key: "operator:KillCard", label: "Kill Switch" },
      { key: "operator:HotkeyConfigurator", label: "Hotkeys" },
    ],
  },
  {
    id: "governance",
    label: "Governance",
    group: "System",
    widgets: [
      { key: "governance:PromotionGatesPanel", label: "Promotion Gates" },
      { key: "governance:DriftOraclePanel", label: "Drift Oracle" },
      { key: "governance:StrategyRegistryFSM", label: "Strategy Registry" },
      { key: "governance:ApprovalQueueWidget", label: "Approval Queue" },
      { key: "governance:AuditLedgerViewer", label: "Audit Ledger" },
      { key: "governance:SCVSLivenessGrid", label: "SCVS Liveness" },
      { key: "governance:HazardMonitorGrid", label: "Hazard Monitor" },
    ],
  },
  {
    id: "ai",
    label: "AI",
    group: "System",
    widgets: [
      { key: "ai:ASKBOrchestrator", label: "ASKB Orchestrator" },
      { key: "ai:CounterfactualPanel", label: "Counterfactual" },
      { key: "ai:NLQConsole", label: "NLQ Console" },
      { key: "ai:EarningsRAG", label: "Earnings RAG" },
      { key: "ai:MultilingualNewsFusion", label: "Multilingual News" },
      { key: "ai:AltSignalDashboard", label: "Alt Signal" },
      { key: "ai:CausalRiskAttribution", label: "Causal Risk" },
      { key: "ai:IntentExecutionPanel", label: "Intent Execution" },
      { key: "ai:SmartMoneyTracker", label: "Smart Money" },
    ],
  },
  {
    id: "testing",
    label: "Testing",
    group: "System",
    widgets: [
      { key: "testing:Backtester", label: "Backtester" },
      { key: "testing:EquityCurveStudio", label: "Equity Curve" },
      { key: "testing:ChampionChallenger", label: "Champion/Challenger" },
      { key: "testing:CalibrationReliability", label: "Calibration" },
      { key: "testing:ParameterSweep", label: "Parameter Sweep" },
      { key: "testing:MonteCarloPaths", label: "Monte Carlo" },
      { key: "testing:ForwardTester", label: "Forward Tester" },
      { key: "testing:WalkForwardHarness", label: "Walk Forward" },
      { key: "testing:ReplayHarness", label: "Replay Harness" },
      { key: "testing:RegimeShiftBoard", label: "Regime Shift" },
    ],
  },
  {
    id: "observatory",
    label: "Observatory",
    group: "System",
    widgets: [
      { key: "observatory:ReasoningStream",    label: "Reasoning Stream" },
      { key: "observatory:TraderClusters",     label: "Trader Clusters" },
      { key: "observatory:CausalGraph",        label: "Causal Graph" },
      { key: "observatory:RegimeMap",          label: "Regime Map" },
      { key: "observatory:Uncertainty",        label: "Uncertainty" },
      { key: "observatory:Confidence",         label: "Confidence Evolution" },
      { key: "observatory:RepoEvolution",      label: "Repository Evolution" },
      { key: "observatory:RuntimeHealth",      label: "Runtime Health" },
      { key: "observatory:ArchDrift",          label: "Architecture Drift" },
      { key: "observatory:MutationTracking",   label: "Mutation Tracking" },
      { key: "observatory:Optimization",       label: "Optimization Candidates" },
      { key: "observatory:EventThroughput",    label: "Event Throughput" },
      { key: "observatory:CognitionLatency",   label: "Cognition Latency" },
      { key: "observatory:GovernanceActions",  label: "Governance Actions" },
      { key: "observatory:MemoryGrowth",       label: "Memory Growth" },
      { key: "observatory:SimulationState",    label: "Simulation State" },
      { key: "observatory:Orchestration",      label: "Orchestration Graph" },
    ],
  },
  {
    id: "indira",
    label: "Indira",
    group: "System",
    widgets: [
      { key: "indira:ConsciousnessPanel", label: "Consciousness Panel" },
      { key: "indira:IndiraLearningMode", label: "Learning Panel" },
      { key: "indira:CognitiveStream", label: "Cognitive Stream" },
    ],
  },
  {
    id: "dyon",
    label: "Dyon",
    group: "System",
    widgets: [
      { key: "dyon:Workspace", label: "Engineering Workspace" },
      { key: "dyon:DyonLearningMode", label: "Learning Panel" },
      { key: "dyon:ArchitectureStream", label: "Architecture Stream" },
    ],
  },
  {
    id: "memory",
    label: "Memory Layer",
    group: "System",
    widgets: [
      { key: "memory:Snapshot",        label: "Memory Snapshot" },
      { key: "memory:Timeline",        label: "Cognition Timeline" },
      { key: "memory:Search",          label: "Keyword Search" },
      { key: "memory:Compression",     label: "Compression Stats" },
      { key: "memory:StrategyStore",   label: "Strategy Store" },
      { key: "memory:TraderStore",     label: "Trader Store" },
      { key: "memory:GovernanceStore", label: "Governance Store" },
      { key: "memory:RuntimeStore",    label: "Runtime Events" },
    ],
  },
  {
    id: "fabric",
    label: "Event Fabric",
    group: "System",
    widgets: [
      { key: "fabric:Authority",    label: "Bus Authority" },
      { key: "fabric:EventStream",  label: "Event Stream" },
      { key: "fabric:Tracing",      label: "Trace Viewer" },
      { key: "fabric:Lineage",      label: "Causality Graph" },
      { key: "fabric:Bridges",      label: "Bridge Status" },
      { key: "fabric:Persistence",  label: "Persistence Stats" },
    ],
  },
  {
    id: "simulation",
    label: "Simulation",
    group: "System",
    widgets: [
      { key: "simulation:Market",     label: "Synthetic Market" },
      { key: "simulation:Arena",      label: "Adversarial Arena" },
      { key: "simulation:Crowd",      label: "Crowd Psychology" },
      { key: "simulation:Reflexive",  label: "Reflexive Engine" },
      { key: "simulation:Volatility", label: "Volatility Cascade" },
      { key: "simulation:Liquidity",  label: "Liquidity Warfare" },
      { key: "simulation:Macro",      label: "Macro Stress" },
      { key: "simulation:Exchange",   label: "Exchange Failure" },
      { key: "simulation:Latency",    label: "Latency Warfare" },
    ],
  },
  // ── Analysis ───────────────────────────────────────────────────────────────
  {
    id: "market",
    label: "Market Context",
    group: "Analysis",
    widgets: [
      { key: "market:Watchlist", label: "Watchlist" },
      { key: "market:HotMovers", label: "Hot Movers" },
      { key: "market:SentimentGauge", label: "Sentiment" },
      { key: "market:FearGreed", label: "Fear & Greed" },
      { key: "market:PutCallRatio", label: "Put/Call Ratio" },
      { key: "market:LongShortRatio", label: "Long/Short" },
      { key: "market:OpenInterestPanel", label: "Open Interest" },
      { key: "market:IVSurface", label: "IV Surface" },
    ],
  },
  {
    id: "onchain",
    label: "On-Chain",
    group: "Analysis",
    widgets: [
      { key: "onchain:WhaleWatcher", label: "Whale Watcher" },
      { key: "onchain:ExchangeFlows", label: "Exchange Flows" },
      { key: "onchain:StablecoinSupply", label: "Stablecoin Supply" },
      { key: "onchain:TVLDashboard", label: "TVL Dashboard" },
      { key: "onchain:OpenInterestMatrix", label: "OI Matrix" },
    ],
  },
  {
    id: "orderflow",
    label: "Order Flow",
    group: "Analysis",
    widgets: [
      { key: "orderflow:LiquidityHeatmap", label: "Liquidity Heatmap" },
      { key: "orderflow:DOMClickLadder", label: "DOM Ladder" },
      { key: "orderflow:FootprintChart", label: "Footprint" },
      { key: "orderflow:CVDChart", label: "CVD" },
      { key: "orderflow:AggressorRatio", label: "Aggressor Ratio" },
      { key: "orderflow:SweepIcebergMonitor", label: "Sweep/Iceberg" },
    ],
  },
  {
    id: "charting",
    label: "Charting",
    group: "Analysis",
    widgets: [
      { key: "charting:tools", label: "Drawing Tools" },
      { key: "charting:chart", label: "Chart" },
      { key: "charting:vp", label: "Volume Profile" },
      { key: "charting:rsi", label: "RSI" },
      { key: "charting:macd", label: "MACD" },
      { key: "charting:stoch", label: "Stochastic" },
      { key: "charting:atr", label: "ATR" },
      { key: "charting:adx", label: "ADX" },
      { key: "charting:type", label: "Chart Type" },
    ],
  },
  // ── Trading ────────────────────────────────────────────────────────────────
  {
    id: "positions",
    label: "Positions & PnL",
    group: "Trading",
    widgets: [
      { key: "positions:IntradayPnLCurve", label: "Intraday PnL" },
      { key: "positions:DrawdownCurve", label: "Drawdown" },
      { key: "positions:OpenOrdersPanel", label: "Open Orders" },
      { key: "positions:ExposureBreakdown", label: "Exposure" },
      { key: "positions:FillsHistory", label: "Fills History" },
      { key: "positions:FundingHistory", label: "Funding History" },
      { key: "positions:RiskParityAllocator", label: "Risk Parity" },
    ],
  },
  {
    id: "trading",
    label: "Trading",
    group: "Trading",
    widgets: [
      { key: "trading:AlgoOrderBuilder", label: "Algo Orders" },
      { key: "trading:ConditionalBracketBuilder", label: "Brackets" },
      { key: "trading:BasketOrderEditor", label: "Basket Orders" },
      { key: "trading:PreTradeSlippageSim", label: "Slippage Sim" },
      { key: "trading:OrderHotkeysPanel", label: "Order Hotkeys" },
    ],
  },
  {
    id: "risk",
    label: "Risk",
    group: "Trading",
    widgets: [
      { key: "risk:OptionsChain", label: "Options Chain" },
      { key: "risk:GreeksPanel", label: "Greeks" },
      { key: "risk:LiqCalc", label: "Liq Calc" },
      { key: "risk:ScenarioBook", label: "Scenarios" },
      { key: "risk:CorrelationMatrix", label: "Correlation" },
    ],
  },
  // ── Asset pages ────────────────────────────────────────────────────────────
  {
    id: "spot",
    label: "Spot",
    group: "Assets",
    widgets: [
      { key: "spot:chart", label: "Chart" },
      { key: "spot:depth", label: "Depth Ladder" },
      { key: "spot:tape", label: "Time & Sales" },
      { key: "spot:order", label: "Order Form" },
      { key: "spot:positions", label: "Positions" },
      { key: "spot:sltp", label: "SL/TP" },
      { key: "spot:coherence", label: "Coherence" },
      { key: "spot:news", label: "News" },
    ],
  },
  {
    id: "perps",
    label: "Perps",
    group: "Assets",
    widgets: [
      { key: "perps:chart", label: "Chart" },
      { key: "perps:funding", label: "Funding Rate" },
      { key: "perps:liq", label: "Liquidation Map" },
      { key: "perps:order", label: "Order Form" },
      { key: "perps:positions", label: "Positions" },
      { key: "perps:sltp", label: "SL/TP" },
      { key: "perps:coherence", label: "Coherence" },
      { key: "perps:oracle", label: "Oracle Spread" },
    ],
  },
  {
    id: "dex",
    label: "DEX",
    group: "Assets",
    widgets: [
      { key: "dex:chart", label: "Chart" },
      { key: "dex:route", label: "Route Graph" },
      { key: "dex:pool", label: "Pool Health" },
      { key: "dex:swap", label: "Swap Form" },
      { key: "dex:positions", label: "Positions" },
      { key: "dex:sltp", label: "SL/TP" },
      { key: "dex:coherence", label: "Coherence" },
      { key: "dex:gas", label: "Gas Estimator" },
    ],
  },
  {
    id: "forex",
    label: "Forex",
    group: "Assets",
    widgets: [
      { key: "forex:chart", label: "Chart" },
      { key: "forex:session", label: "Session Clock" },
      { key: "forex:depth", label: "Depth Ladder" },
      { key: "forex:order", label: "Order Form" },
      { key: "forex:positions", label: "Positions" },
      { key: "forex:sltp", label: "SL/TP" },
      { key: "forex:calendar", label: "Economic Calendar" },
      { key: "forex:cbrates", label: "CB Rates" },
      { key: "forex:carry", label: "Carry Ladder" },
      { key: "forex:strength", label: "Currency Strength" },
      { key: "forex:pipcalc", label: "Pip Calc" },
      { key: "forex:coherence", label: "Coherence" },
    ],
  },
  {
    id: "stocks",
    label: "Stocks",
    group: "Assets",
    widgets: [
      { key: "stocks:chart", label: "Chart" },
      { key: "stocks:level2", label: "Level 2" },
      { key: "stocks:tape", label: "Time & Sales" },
      { key: "stocks:order", label: "Order Form" },
      { key: "stocks:positions", label: "Positions" },
      { key: "stocks:sltp", label: "SL/TP" },
      { key: "stocks:fundamentals", label: "Fundamentals" },
      { key: "stocks:ratings", label: "Analyst Ratings" },
      { key: "stocks:insider", label: "Insider Tx" },
      { key: "stocks:short", label: "Short Interest" },
      { key: "stocks:sectors", label: "Sector Heatmap" },
      { key: "stocks:earnings", label: "Earnings" },
      { key: "stocks:coherence", label: "Coherence" },
    ],
  },
  {
    id: "nft",
    label: "NFT",
    group: "Assets",
    widgets: [
      { key: "nft:floor", label: "Floor Chart" },
      { key: "nft:trait-grid", label: "Trait Floor" },
      { key: "nft:sweep", label: "Sweep Cart" },
      { key: "nft:bid-ladder", label: "Bid Ladder" },
      { key: "nft:rarity", label: "Rarity Lens" },
      { key: "nft:order", label: "Order Form" },
      { key: "nft:positions", label: "Positions" },
      { key: "nft:sltp", label: "SL/TP" },
      { key: "nft:volume", label: "Collection Volume" },
      { key: "nft:coherence", label: "Coherence" },
    ],
  },
  {
    id: "memecoin",
    label: "Memecoin",
    group: "Assets",
    widgets: [
      { key: "memecoin:chart", label: "Chart" },
      { key: "memecoin:pair-card", label: "Pair Card" },
      { key: "memecoin:rug", label: "Rug Score" },
      { key: "memecoin:holders", label: "Holder Dist." },
      { key: "memecoin:tape", label: "Time & Sales" },
      { key: "memecoin:sniper-queue", label: "Sniper Queue" },
      { key: "memecoin:copy-leaders", label: "Copy Leaders" },
      { key: "memecoin:signal-tracker", label: "Signal Tracker" },
      { key: "memecoin:order-copy", label: "Copy Order" },
      { key: "memecoin:sltp-normal", label: "SL/TP Normal" },
      { key: "memecoin:sltp-sniper", label: "SL/TP Sniper" },
      { key: "memecoin:coherence", label: "Coherence" },
      { key: "memecoin:alerts", label: "Alerts" },
      { key: "memecoin:launch-firehose", label: "Launch Firehose" },
      { key: "memecoin:dev-dump", label: "Dev Dump" },
      { key: "memecoin:bundle", label: "Bundle Detector" },
      { key: "memecoin:honeypot", label: "Honeypot" },
      { key: "memecoin:wallet-cluster", label: "Wallet Cluster" },
    ],
  },
];

// ── Store ─────────────────────────────────────────────────────────────────────

const KEY = "dix.dash2.widget-visibility.v1";

type VisibilityState = Record<string, boolean>;

function loadState(): VisibilityState {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const result: VisibilityState = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === "boolean") result[k] = v;
    }
    return result;
  } catch {
    return {};
  }
}

let _state: VisibilityState = loadState();
let _panelOpen = false;
const _listeners = new Set<() => void>();

function _emit() {
  for (const fn of _listeners) fn();
}

function _subscribe(fn: () => void): () => void {
  _listeners.add(fn);
  return () => {
    _listeners.delete(fn);
  };
}

function _persist() {
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(KEY, JSON.stringify(_state));
    }
  } catch {
    /* storage full / blocked */
  }
}

// ── Getters (used as useSyncExternalStore snapshots) ──────────────────────────

function _getState(): VisibilityState {
  return _state;
}

function _getPanelOpen(): boolean {
  return _panelOpen;
}

// ── Mutators ──────────────────────────────────────────────────────────────────

export function setWidgetVisible(key: string, visible: boolean): void {
  _state = { ..._state, [key]: visible };
  _persist();
  _emit();
}

export function setPageAllVisible(pageId: string, visible: boolean): void {
  const page = WIDGET_REGISTRY.find((p) => p.id === pageId);
  if (!page) return;
  const next = { ..._state };
  for (const w of page.widgets) next[w.key] = visible;
  _state = next;
  _persist();
  _emit();
}

export function resetAllVisible(): void {
  _state = {};
  try {
    if (typeof window !== "undefined") window.localStorage.removeItem(KEY);
  } catch {
    /* storage full / blocked */
  }
  _emit();
}

export function setWidgetPanelOpen(open: boolean): void {
  _panelOpen = open;
  _emit();
}

// ── Pure check (non-reactive, call inside render closures) ─────────────────────

export function isWidgetVisible(key: string, snap?: VisibilityState): boolean {
  const s = snap ?? _state;
  return s[key] !== false;
}

// ── React hooks ───────────────────────────────────────────────────────────────

export function useWidgetVisible(key: string): boolean {
  const snap = useSyncExternalStore(_subscribe, _getState, _getState);
  return snap[key] !== false;
}

export function useWidgetVisibilitySnapshot(): VisibilityState {
  return useSyncExternalStore(_subscribe, _getState, _getState);
}

export function useWidgetPanelOpen(): boolean {
  return useSyncExternalStore(_subscribe, _getPanelOpen, _getPanelOpen);
}

/**
 * Wraps AssetGrid ITEMS so that each item's render function returns null when
 * its widget is hidden. Passes the full item array unchanged (preserving grid
 * layout positions); only the rendered content is suppressed.
 */
export function useVisibilityWrappedItems<
  T extends { i: string; render: () => ReactNode },
>(pageId: string, items: T[]): T[] {
  const snap = useWidgetVisibilitySnapshot();
  return useMemo(
    () =>
      items.map((item) => ({
        ...item,
        render: () =>
          snap[`${pageId}:${item.i}`] !== false ? item.render() : null,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [snap],
  );
}
