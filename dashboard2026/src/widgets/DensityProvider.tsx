/**
 * DensityProvider — Layout density control (Tier 4.3).
 *
 * Controls spacing, font sizes, and widget padding across
 * the entire dashboard. Three modes:
 * - compact: minimal padding, small text (for multi-monitor)
 * - comfortable: balanced (default)
 * - spacious: large padding, more whitespace
 */
import React, { createContext, useContext, useState } from "react";

type Density = "compact" | "comfortable" | "spacious";

interface DensityConfig {
  padding: string;
  gap: string;
  fontSize: string;
  headerSize: string;
  widgetMinH: string;
}

const DENSITY_CONFIGS: Record<Density, DensityConfig> = {
  compact: {
    padding: "p-1",
    gap: "gap-1",
    fontSize: "text-xs",
    headerSize: "text-sm",
    widgetMinH: "min-h-[120px]",
  },
  comfortable: {
    padding: "p-3",
    gap: "gap-3",
    fontSize: "text-sm",
    headerSize: "text-base",
    widgetMinH: "min-h-[200px]",
  },
  spacious: {
    padding: "p-5",
    gap: "gap-5",
    fontSize: "text-base",
    headerSize: "text-lg",
    widgetMinH: "min-h-[280px]",
  },
};

interface DensityContextValue {
  density: Density;
  config: DensityConfig;
  setDensity: (d: Density) => void;
}

const DensityContext = createContext<DensityContextValue>({
  density: "comfortable",
  config: DENSITY_CONFIGS.comfortable,
  setDensity: () => {},
});

export const useDensity = () => useContext(DensityContext);

interface Props {
  children: React.ReactNode;
  defaultDensity?: Density;
}

export const DensityProvider: React.FC<Props> = ({
  children,
  defaultDensity = "comfortable",
}) => {
  const [density, setDensity] = useState<Density>(defaultDensity);
  const config = DENSITY_CONFIGS[density];

  return (
    <DensityContext.Provider value={{ density, config, setDensity }}>
      <div className={`${config.fontSize} ${config.gap}`}>{children}</div>
    </DensityContext.Provider>
  );
};

export const DensitySelector: React.FC = () => {
  const { density, setDensity } = useDensity();

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-400">Density:</span>
      {(["compact", "comfortable", "spacious"] as Density[]).map((d) => (
        <button
          key={d}
          onClick={() => setDensity(d)}
          className={`px-2 py-0.5 text-xs rounded ${
            density === d ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300"
          }`}
        >
          {d}
        </button>
      ))}
    </div>
  );
};

export default DensityProvider;
