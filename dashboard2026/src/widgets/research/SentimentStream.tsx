import React from 'react';

interface SentimentEntry {
  source: string;
  ticker: string;
  score: number;
  ts: string;
}

export function SentimentStream() {
  const [entries, _setEntries] = React.useState<SentimentEntry[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Sentiment Stream</h3>
      {entries.length === 0 ? (
        <p className="text-xs text-gray-500">No sentiment signals</p>
      ) : (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {entries.map((e, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <span className="text-gray-400">{e.source}</span>
              <span className="text-gray-300 font-mono">{e.ticker}</span>
              <span className={e.score > 0 ? 'text-green-400' : 'text-red-400'}>
                {e.score > 0 ? '+' : ''}{e.score.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
