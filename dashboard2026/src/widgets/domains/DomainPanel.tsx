/**
 * Domain Panel widget (BUILD-DIRECTIVE §24 — domain panels).
 *
 * Shows per-domain status:
 * - Current trading mode
 * - Semi-auto policy thresholds
 * - Active positions (if any)
 * - Domain-specific metrics
 */

import { useState } from 'react';

interface DomainStatus {
  domain: string;
  trading_mode: string;
  semi_auto_threshold_usd: number;
  active_positions: number;
  pnl_today_usd: number;
}

export function DomainPanel() {
  const [domains] = useState<DomainStatus[]>([
    {
      domain: 'NORMAL',
      trading_mode: 'FULL_AUTO',
      semi_auto_threshold_usd: 500,
      active_positions: 0,
      pnl_today_usd: 0,
    },
    {
      domain: 'COPY_TRADING',
      trading_mode: 'SEMI_AUTO',
      semi_auto_threshold_usd: 200,
      active_positions: 0,
      pnl_today_usd: 0,
    },
    {
      domain: 'MEMECOIN',
      trading_mode: 'MANUAL',
      semi_auto_threshold_usd: 50,
      active_positions: 0,
      pnl_today_usd: 0,
    },
  ]);

  return (
    <div className="domain-panel">
      <h3>Trading Domains</h3>
      {domains.map((d) => (
        <div key={d.domain} className="domain-card">
          <div className="domain-header">
            <span className="domain-name">{d.domain}</span>
            <span className={`mode-badge mode-${d.trading_mode.toLowerCase()}`}>
              {d.trading_mode}
            </span>
          </div>
          <div className="domain-metrics">
            <div className="metric">
              <label>Semi-Auto Threshold</label>
              <span>${d.semi_auto_threshold_usd}</span>
            </div>
            <div className="metric">
              <label>Active Positions</label>
              <span>{d.active_positions}</span>
            </div>
            <div className="metric">
              <label>P&L Today</label>
              <span className={d.pnl_today_usd >= 0 ? 'positive' : 'negative'}>
                ${d.pnl_today_usd.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
