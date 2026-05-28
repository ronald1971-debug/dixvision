/**
 * HeatmapPanel — Correlation/performance heatmap (Tier 4.3).
 *
 * Displays archetype/strategy performance across regimes
 * as a color-coded heatmap matrix.
 */
import React from "react";

interface HeatmapCell {
  row: string;
  col: string;
  value: number;  // -1 to 1
}

interface Props {
  title?: string;
  data?: HeatmapCell[];
  rows?: string[];
  cols?: string[];
}

const colorScale = (v: number): string => {
  if (v > 0.5) return "bg-green-500";
  if (v > 0.2) return "bg-green-700";
  if (v > -0.2) return "bg-gray-600";
  if (v > -0.5) return "bg-red-700";
  return "bg-red-500";
};

export const HeatmapPanel: React.FC<Props> = ({
  title = "Performance Heatmap",
  data = [],
  rows = ["Macro", "Trend", "Quant", "Discretionary", "Event", "Crypto", "Meta"],
  cols = ["Bull", "Bear", "Range", "Volatile", "Crisis"],
}) => {
  const getCell = (row: string, col: string): number => {
    const cell = data.find((d) => d.row === row && d.col === col);
    return cell?.value ?? 0;
  };

  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
      <h3 className="text-sm font-semibold text-white mb-2">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left text-gray-400 p-1"></th>
              {cols.map((col) => (
                <th key={col} className="text-center text-gray-400 p-1">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row}>
                <td className="text-gray-300 p-1">{row}</td>
                {cols.map((col) => {
                  const val = getCell(row, col);
                  return (
                    <td key={col} className="p-1">
                      <div className={`w-full h-6 rounded ${colorScale(val)} flex items-center justify-center`}>
                        <span className="text-white text-[10px]">
                          {(val * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default HeatmapPanel;
