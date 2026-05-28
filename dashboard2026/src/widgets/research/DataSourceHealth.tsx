import React from 'react';

interface SourceHealth {
  name: string;
  type: 'x' | 'reddit' | 'tradingview' | 'onchain' | 'exchange';
  status: 'connected' | 'degraded' | 'offline';
  lastFetch: string;
  signalsPerHour: number;
}

export function DataSourceHealth() {
  const [sources, _setSources] = React.useState<SourceHealth[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Data Source Health</h3>
      {sources.length === 0 ? (
        <p className="text-xs text-gray-500">No data sources configured</p>
      ) : (
        <div className="space-y-1">
          {sources.map((s) => (
            <div key={s.name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${
                  s.status === 'connected' ? 'bg-green-400' :
                  s.status === 'degraded' ? 'bg-yellow-400' : 'bg-red-400'
                }`} />
                <span className="text-gray-300">{s.name}</span>
              </div>
              <span className="text-gray-500">{s.signalsPerHour}/hr</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
