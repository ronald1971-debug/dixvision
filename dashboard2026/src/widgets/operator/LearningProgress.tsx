/**
 * Learning Progress widget (BUILD-DIRECTIVE §24 — widget 4/6).
 *
 * Shows capability tier progress for each subsystem.
 * Displays evidence-based promotion status.
 */

import { useState, useEffect } from 'react';

interface SubsystemProgress {
  subsystem: string;
  current_tier: number;
  tier_name: string;
  next_requirements: Record<string, number>;
}

const TIER_NAMES = ['READ_ONLY', 'RESEARCH', 'SIMULATION', 'PROPOSAL', 'GOVERNED_PAPER', 'LIVE'];

export function LearningProgress() {
  const [progress, setProgress] = useState<SubsystemProgress[]>([]);

  useEffect(() => {
    // In production, fetches from /api/learning/progress
    setProgress([
      {
        subsystem: 'intelligence_engine',
        current_tier: 2,
        tier_name: 'SIMULATION',
        next_requirements: { backtest_sharpe_avg: 1.0, strategies_proposed: 5 },
      },
      {
        subsystem: 'evolution_engine',
        current_tier: 1,
        tier_name: 'RESEARCH',
        next_requirements: { backtests_completed: 50 },
      },
      {
        subsystem: 'learning_engine',
        current_tier: 2,
        tier_name: 'SIMULATION',
        next_requirements: { backtest_sharpe_avg: 1.0 },
      },
    ]);
  }, []);

  return (
    <div className="learning-progress">
      <h3>Learning Progress</h3>
      {progress.map((p) => (
        <div key={p.subsystem} className="progress-row">
          <div className="subsystem-name">{p.subsystem}</div>
          <div className="tier-bar">
            {TIER_NAMES.map((name, i) => (
              <span key={name} className={`tier-dot ${i <= p.current_tier ? 'active' : ''}`}>
                {i === p.current_tier ? name : ''}
              </span>
            ))}
          </div>
          <div className="next-requirements">
            {Object.entries(p.next_requirements).map(([k, v]) => (
              <span key={k} className="requirement">
                {k}: {v}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
