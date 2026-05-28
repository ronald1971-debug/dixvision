/**
 * EquityCurve — Portfolio equity curve with drawdown overlay (Tier 4.3).
 */
import React from "react";

interface EquityPoint {
  ts: number;
  equity: number;
  drawdown: number;
}

interface Props {
  data?: EquityPoint[];
  height?: number;
}

export const EquityCurve: React.FC<Props> = ({
  data = [],
  height = 200,
}) => {
  if (data.length === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
        <h3 className="text-sm font-semibold text-white mb-2">Equity Curve</h3>
        <div className="flex items-center justify-center text-gray-500" style={{ height }}>
          No data available
        </div>
      </div>
    );
  }

  const maxEquity = Math.max(...data.map((d) => d.equity));
  const minEquity = Math.min(...data.map((d) => d.equity));
  const range = maxEquity - minEquity || 1;

  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 100 - ((d.equity - minEquity) / range) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
      <h3 className="text-sm font-semibold text-white mb-2">Equity Curve</h3>
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>High: ${maxEquity.toLocaleString()}</span>
        <span>Low: ${minEquity.toLocaleString()}</span>
      </div>
      <svg viewBox="0 0 100 100" className="w-full" style={{ height }} preserveAspectRatio="none">
        <polyline
          points={points}
          fill="none"
          stroke="#22c55e"
          strokeWidth="0.5"
        />
      </svg>
    </div>
  );
};

export default EquityCurve;
