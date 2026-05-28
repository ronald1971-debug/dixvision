/**
 * RegimeTimeline — Visual timeline of market regime transitions (Tier 4.3).
 */
import React from "react";

interface RegimeSegment {
  regime: string;
  start_ts: number;
  end_ts: number;
  confidence: number;
}

interface Props {
  segments?: RegimeSegment[];
}

const REGIME_COLORS: Record<string, string> = {
  TRENDING_BULL: "bg-green-500",
  TRENDING_BEAR: "bg-red-500",
  VOLATILE: "bg-yellow-500",
  RANGING: "bg-blue-500",
  CRISIS: "bg-purple-600",
  EQUILIBRIUM: "bg-gray-500",
};

export const RegimeTimeline: React.FC<Props> = ({ segments = [] }) => {
  if (segments.length === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
        <h3 className="text-sm font-semibold text-white mb-2">Regime Timeline</h3>
        <div className="h-8 bg-gray-800 rounded flex items-center justify-center text-xs text-gray-500">
          No regime data
        </div>
      </div>
    );
  }

  const totalDuration = segments.reduce((acc, s) => acc + (s.end_ts - s.start_ts), 0);

  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
      <h3 className="text-sm font-semibold text-white mb-2">Regime Timeline</h3>
      <div className="flex h-8 rounded overflow-hidden">
        {segments.map((seg, i) => {
          const width = ((seg.end_ts - seg.start_ts) / totalDuration) * 100;
          const color = REGIME_COLORS[seg.regime] || "bg-gray-600";
          return (
            <div
              key={i}
              className={`${color} flex items-center justify-center text-[10px] text-white font-medium`}
              style={{ width: `${width}%`, opacity: 0.5 + seg.confidence * 0.5 }}
              title={`${seg.regime} (${(seg.confidence * 100).toFixed(0)}%)`}
            >
              {width > 10 ? seg.regime.slice(0, 4) : ""}
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2 mt-2">
        {Object.entries(REGIME_COLORS).map(([name, color]) => (
          <span key={name} className="flex items-center gap-1 text-[10px] text-gray-400">
            <span className={`w-2 h-2 rounded-full ${color}`} />
            {name}
          </span>
        ))}
      </div>
    </div>
  );
};

export default RegimeTimeline;
