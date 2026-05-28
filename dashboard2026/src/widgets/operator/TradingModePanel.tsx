/**
 * Trading Mode Panel widget (BUILD-DIRECTIVE §24 — widget 2/6).
 *
 * Per-domain trading mode selector:
 * - NORMAL domain: MANUAL / SEMI_AUTO / FULL_AUTO
 * - COPY_TRADING domain: MANUAL / SEMI_AUTO / FULL_AUTO
 * - MEMECOIN domain: MANUAL / SEMI_AUTO / FULL_AUTO
 *
 * No confirmation modals. Immediate effect.
 */

import { useState, useEffect } from 'react';

type TradingMode = 'MANUAL' | 'SEMI_AUTO' | 'FULL_AUTO';
type Domain = 'NORMAL' | 'COPY_TRADING' | 'MEMECOIN';

export function TradingModePanel() {
  const [modes, setModes] = useState<Record<Domain, TradingMode>>({
    NORMAL: 'FULL_AUTO',
    COPY_TRADING: 'SEMI_AUTO',
    MEMECOIN: 'MANUAL',
  });

  useEffect(() => {
    fetch('/api/authority/state')
      .then((r) => r.json())
      .then((data) => {
        if (data.trading_modes) setModes(data.trading_modes);
      })
      .catch(() => {});
  }, []);

  const setMode = (domain: Domain, mode: TradingMode) => {
    fetch('/api/authority/trading-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, mode }),
    }).then(() => setModes((m) => ({ ...m, [domain]: mode })));
  };

  const domains: Domain[] = ['NORMAL', 'COPY_TRADING', 'MEMECOIN'];

  return (
    <div className="trading-mode-panel">
      <h3>Trading Mode by Domain</h3>
      {domains.map((domain) => (
        <div key={domain} className="domain-row">
          <span className="domain-label">{domain}</span>
          <select
            value={modes[domain]}
            onChange={(e) => setMode(domain, e.target.value as TradingMode)}
          >
            <option value="MANUAL">MANUAL</option>
            <option value="SEMI_AUTO">SEMI_AUTO</option>
            <option value="FULL_AUTO">FULL_AUTO</option>
          </select>
        </div>
      ))}
    </div>
  );
}
