/**
 * Operator Authority Switches widget (BUILD-DIRECTIVE §24 — widget 1/6).
 *
 * Three toggle controls for the orthogonal authority axes:
 * - Learning: OFF / SHADOW / FULL
 * - Practice: OFF / ON
 * - LiveExecution: BLOCKED / ARMED
 *
 * No confirmation modals. No cooldowns. Immediate state change.
 */

import { useState, useEffect } from 'react';

interface AuthorityState {
  learning: 'OFF' | 'SHADOW' | 'FULL';
  practice: 'OFF' | 'ON';
  live_execution: 'BLOCKED' | 'ARMED';
}

export function AuthoritySwitches() {
  const [state, setState] = useState<AuthorityState>({
    learning: 'FULL',
    practice: 'ON',
    live_execution: 'BLOCKED',
  });

  useEffect(() => {
    fetch('/api/authority/state')
      .then((r) => r.json())
      .then((data) => setState(data))
      .catch(() => {});
  }, []);

  const setLearning = (value: string) => {
    fetch('/api/authority/learning', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    }).then(() => setState((s) => ({ ...s, learning: value as AuthorityState['learning'] })));
  };

  const setPractice = (value: string) => {
    fetch('/api/authority/practice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    }).then(() => setState((s) => ({ ...s, practice: value as AuthorityState['practice'] })));
  };

  const setLiveExecution = (value: string) => {
    fetch('/api/authority/live-execution', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    }).then(() =>
      setState((s) => ({ ...s, live_execution: value as AuthorityState['live_execution'] }))
    );
  };

  return (
    <div className="authority-switches">
      <h3>Operator Authority</h3>
      <div className="switch-group">
        <label>Learning</label>
        <select value={state.learning} onChange={(e) => setLearning(e.target.value)}>
          <option value="OFF">OFF</option>
          <option value="SHADOW">SHADOW</option>
          <option value="FULL">FULL</option>
        </select>
      </div>
      <div className="switch-group">
        <label>Practice</label>
        <select value={state.practice} onChange={(e) => setPractice(e.target.value)}>
          <option value="OFF">OFF</option>
          <option value="ON">ON</option>
        </select>
      </div>
      <div className="switch-group">
        <label>Live Execution</label>
        <select value={state.live_execution} onChange={(e) => setLiveExecution(e.target.value)}>
          <option value="BLOCKED">BLOCKED</option>
          <option value="ARMED">ARMED</option>
        </select>
      </div>
    </div>
  );
}
