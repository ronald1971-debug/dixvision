import React from 'react';

interface RegimeState {
  current: string;
  confidence: number;
  transition: string | null;
  transitionSpeed: number;
  history: { regime: string; duration: string }[];
}

export function RegimeClassifier() {
  const [state, _setState] = React.useState<RegimeState | null>(null);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Regime Classifier</h3>
      {!state ? (
        <p className="text-xs text-gray-500">Awaiting market data</p>
      ) : (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-lg font-bold text-blue-400">{state.current}</span>
            <span className="text-xs text-gray-500">
              {(state.confidence * 100).toFixed(0)}% conf
            </span>
          </div>
          {state.transition && (
            <div className="text-xs text-yellow-400 mb-2">
              Transitioning to: {state.transition}
            </div>
          )}
          <div className="space-y-1">
            {state.history.slice(0, 5).map((h, i) => (
              <div key={i} className="flex justify-between text-xs text-gray-500">
                <span>{h.regime}</span>
                <span>{h.duration}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
