import React from 'react';

interface ArchetypeStats {
  group: string;
  activeCount: number;
  avgReliability: number;
  topPerformer: string;
  regimeAlignment: number;
}

export function ArchetypePerformance() {
  const [stats, _setStats] = React.useState<ArchetypeStats[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Archetype Performance</h3>
      {stats.length === 0 ? (
        <p className="text-xs text-gray-500">No archetype data</p>
      ) : (
        <div className="space-y-2">
          {stats.map((s) => (
            <div key={s.group} className="flex items-center justify-between text-xs">
              <span className="text-gray-300">{s.group}</span>
              <span className="text-gray-500">{s.activeCount} active</span>
              <span className={s.avgReliability > 0.6 ? 'text-green-400' : 'text-yellow-400'}>
                {(s.avgReliability * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
