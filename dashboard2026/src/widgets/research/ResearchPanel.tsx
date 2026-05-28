/**
 * Research Panel widget (BUILD-DIRECTIVE §24 — research widget).
 *
 * Interface for submitting and viewing browser research tasks.
 * Shows active research tasks and their results.
 */

import { useState } from 'react';

interface ResearchTask {
  id: string;
  task_type: string;
  query: string;
  status: string;
}

export function ResearchPanel() {
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [query, setQuery] = useState('');
  const [taskType, setTaskType] = useState('TRADER_PROFILE');

  const submitResearch = () => {
    if (!query.trim()) return;
    fetch('/api/research/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_type: taskType, query }),
    })
      .then((r) => r.json())
      .then((data) => {
        setTasks((t) => [...t, { id: Date.now().toString(), ...data }]);
        setQuery('');
      });
  };

  return (
    <div className="research-panel">
      <h3>Browser Research</h3>
      <div className="research-form">
        <select value={taskType} onChange={(e) => setTaskType(e.target.value)}>
          <option value="TRADER_PROFILE">Trader Profile</option>
          <option value="MARKET_ANALYSIS">Market Analysis</option>
          <option value="STRATEGY_REPORT">Strategy Report</option>
          <option value="NEWS_DEEP_DIVE">News Deep Dive</option>
          <option value="ACADEMIC_PAPER">Academic Paper</option>
        </select>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Research query..."
          onKeyDown={(e) => e.key === 'Enter' && submitResearch()}
        />
        <button onClick={submitResearch}>Submit</button>
      </div>
      <div className="research-tasks">
        {tasks.map((t) => (
          <div key={t.id} className="task-row">
            <span className="task-type">{t.task_type}</span>
            <span className="task-query">{t.query}</span>
            <span className="task-status">{t.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
