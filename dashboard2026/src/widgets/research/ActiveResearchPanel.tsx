import React, { useEffect } from 'react';

interface ResearchTarget {
  id: string;
  task_type: string;
  query: string;
  status: 'active' | 'completed' | 'queued' | 'failed';
  result?: string;
}

export function ActiveResearchPanel() {
  const [targets, setTargets] = React.useState<ResearchTarget[]>([]);
  const [live, setLive] = React.useState(false);

  useEffect(() => {
    const load = () =>
      fetch('/api/research/tasks')
        .then((r) => r.json())
        .then((data) => {
          setTargets(
            (data.tasks ?? []).map((t: Record<string, unknown>) => ({
              id: String(t.id ?? ''),
              task_type: String(t.task_type ?? ''),
              query: String(t.query ?? ''),
              status: (t.status as 'queued' | 'active' | 'completed' | 'failed') ?? 'queued',
              result: t.result != null ? String(t.result) : undefined,
            }))
          );
          setLive(true);
        })
        .catch(() => setLive(false));

    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const statusColor = (s: string) =>
    s === 'active' || s === 'queued'
      ? 'bg-green-400'
      : s === 'completed'
      ? 'bg-blue-400'
      : 'bg-gray-500';

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-300">Active Research</h3>
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            live ? 'bg-emerald-900 text-emerald-300' : 'bg-amber-900 text-amber-300'
          }`}
        >
          {live ? 'live' : 'mock'}
        </span>
      </div>
      {targets.length === 0 ? (
        <p className="text-xs text-gray-500">No active research tasks. Submit one via the Research Panel.</p>
      ) : (
        <ul className="space-y-2">
          {targets.map((t) => (
            <li key={t.id} className="flex items-start gap-2 text-xs">
              <span className={`mt-1 w-2 h-2 flex-shrink-0 rounded-full ${statusColor(t.status)}`} />
              <div className="flex-1 min-w-0">
                <div className="flex gap-1 items-center">
                  <span className="text-gray-400 font-medium">[{t.task_type}]</span>
                  <span className="text-gray-300 truncate">{t.query}</span>
                </div>
                {t.result && (
                  <p className="mt-0.5 text-gray-500 line-clamp-2">{t.result}</p>
                )}
              </div>
              <span
                className={`flex-shrink-0 text-xs ${
                  t.status === 'completed' ? 'text-blue-400' : 'text-gray-500'
                }`}
              >
                {t.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
