import React from 'react';

interface Atom {
  id: string;
  category: string;
  sourceTrader: string;
  regimeFitness: number;
  observations: number;
  active: boolean;
}

export function AtomRegistry() {
  const [atoms, _setAtoms] = React.useState<Atom[]>([]);
  const [filter, setFilter] = React.useState('');

  const filtered = atoms.filter(
    (a) => !filter || a.category.includes(filter) || a.sourceTrader.includes(filter)
  );

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-300">Atom Registry</h3>
        <span className="text-xs text-gray-500">{atoms.length} atoms</span>
      </div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter..."
        className="w-full text-xs bg-gray-800 text-gray-300 rounded px-2 py-1 mb-2"
      />
      {filtered.length === 0 ? (
        <p className="text-xs text-gray-500">No atoms registered</p>
      ) : (
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {filtered.slice(0, 20).map((a) => (
            <div key={a.id} className="flex items-center justify-between text-xs">
              <span className="text-gray-400">{a.category}</span>
              <span className="text-gray-300">{a.sourceTrader}</span>
              <span className="text-gray-500">{a.observations} obs</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
