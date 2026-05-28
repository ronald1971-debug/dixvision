import React from 'react';

interface DivergenceAlert {
  traderId: string;
  indiraAction: string;
  traderAction: string;
  magnitude: number;
  learningValue: number;
  ts: string;
}

export function DivergenceAlerts() {
  const [alerts, _setAlerts] = React.useState<DivergenceAlert[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Divergence Alerts</h3>
      {alerts.length === 0 ? (
        <p className="text-xs text-gray-500">No divergences detected</p>
      ) : (
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {alerts.map((a, i) => (
            <div key={i} className="border border-gray-700 rounded p-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-300">{a.traderId}</span>
                <span className={a.magnitude > 0.5 ? 'text-red-400' : 'text-yellow-400'}>
                  {(a.magnitude * 100).toFixed(0)}% divergence
                </span>
              </div>
              <div className="text-gray-500 mt-1">
                Indira: {a.indiraAction} vs Trader: {a.traderAction}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
