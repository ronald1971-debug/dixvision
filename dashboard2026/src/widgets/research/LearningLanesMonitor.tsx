import React from 'react';

interface LaneStatus {
  name: string;
  active: boolean;
  eventsPerHour: number;
  lastEvent: string;
  health: 'ok' | 'slow' | 'stalled';
}

export function LearningLanesMonitor() {
  const [lanes, _setLanes] = React.useState<LaneStatus[]>([]);

  return (
    <div className="p-4 bg-gray-900 rounded-lg">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Learning Lanes</h3>
      {lanes.length === 0 ? (
        <p className="text-xs text-gray-500">No active learning lanes</p>
      ) : (
        <div className="space-y-1">
          {lanes.map((l) => (
            <div key={l.name} className="flex items-center justify-between text-xs">
              <span className="text-gray-300">{l.name}</span>
              <div className="flex items-center gap-2">
                <span className="text-gray-500">{l.eventsPerHour}/hr</span>
                <span className={`w-2 h-2 rounded-full ${
                  l.health === 'ok' ? 'bg-green-400' :
                  l.health === 'slow' ? 'bg-yellow-400' : 'bg-red-400'
                }`} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
