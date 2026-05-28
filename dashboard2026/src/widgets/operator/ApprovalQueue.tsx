/**
 * Approval Queue widget (BUILD-DIRECTIVE §24 — widget 3/6).
 *
 * Shows pending semi-auto intents that require operator approval.
 * One-click approve/reject. No confirmation modals.
 */

import { useState, useEffect } from 'react';

interface PendingItem {
  request_id: string;
  domain: string;
  symbol: string;
  side: string;
  notional_usd: number;
  rationale: string;
}

export function ApprovalQueue() {
  const [pending, setPending] = useState<PendingItem[]>([]);

  useEffect(() => {
    const poll = () => {
      fetch('/api/authority/approval-queue')
        .then((r) => r.json())
        .then((data) => setPending(data.pending || []))
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  const approve = (request_id: string) => {
    fetch('/api/authority/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id }),
    }).then(() => setPending((p) => p.filter((i) => i.request_id !== request_id)));
  };

  const reject = (request_id: string) => {
    fetch('/api/authority/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id }),
    }).then(() => setPending((p) => p.filter((i) => i.request_id !== request_id)));
  };

  return (
    <div className="approval-queue">
      <h3>Pending Approvals ({pending.length})</h3>
      {pending.length === 0 && <p className="empty">No pending items</p>}
      {pending.map((item) => (
        <div key={item.request_id} className="approval-item">
          <div className="item-info">
            <span className="symbol">{item.symbol}</span>
            <span className="side">{item.side}</span>
            <span className="notional">${item.notional_usd.toFixed(2)}</span>
            <span className="domain">{item.domain}</span>
          </div>
          <div className="item-actions">
            <button className="approve" onClick={() => approve(item.request_id)}>
              Approve
            </button>
            <button className="reject" onClick={() => reject(item.request_id)}>
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
