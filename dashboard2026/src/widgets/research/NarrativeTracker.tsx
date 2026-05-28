import React from 'react';

interface Narrative {
  theme: string;
  strength: number;
  sources: number;
  alignment: number;
  trend: 'rising' | 'stable' | 'falling';
}

export function NarrativeTracker() {
  const [narratives, _setNarratives] = React.useState<Narrative[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Narrative Tracker</h3>
      {narratives.length === 0 ? (
        <p className="text-xs text-gray-500">No active narratives detected</p>
      ) : (
        <div className="space-y-2">
          {narratives.map((n) => (
            <div key={n.theme} className="text-xs">
              <div className="flex justify-between">
                <span className="text-gray-300">{n.theme}</span>
                <span className={
                  n.trend === 'rising' ? 'text-green-400' :
                  n.trend === 'falling' ? 'text-red-400' : 'text-gray-400'
                }>
                  {n.trend === 'rising' ? '↑' : n.trend === 'falling' ? '↓' : '→'}
                </span>
              </div>
              <div className="w-full bg-gray-700 rounded h-1 mt-1">
                <div
                  className="bg-blue-500 rounded h-1"
                  style={{ width: `${n.strength * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
