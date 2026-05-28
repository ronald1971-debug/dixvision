import React from 'react';

interface Composition {
  id: string;
  atomCount: number;
  diversityScore: number;
  regimeFitness: number;
  validationStatus: 'valid' | 'rejected' | 'pending';
  regime: string;
}

export function CompositionStatus() {
  const [compositions, _setCompositions] = React.useState<Composition[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Strategy Compositions</h3>
      {compositions.length === 0 ? (
        <p className="text-xs text-gray-500">No active compositions</p>
      ) : (
        <div className="space-y-2">
          {compositions.map((c) => (
            <div key={c.id} className="border border-gray-700 rounded p-2">
              <div className="flex justify-between text-xs">
                <span className="text-gray-300">{c.id.slice(0, 8)}</span>
                <span className={
                  c.validationStatus === 'valid' ? 'text-green-400' :
                  c.validationStatus === 'rejected' ? 'text-red-400' : 'text-yellow-400'
                }>
                  {c.validationStatus}
                </span>
              </div>
              <div className="flex gap-3 text-xs text-gray-500 mt-1">
                <span>{c.atomCount} atoms</span>
                <span>div: {(c.diversityScore * 100).toFixed(0)}%</span>
                <span>{c.regime}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
