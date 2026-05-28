/**
 * CommandPalette — Spotlight-style command palette (Tier 4.3).
 *
 * Provides quick access to all operator actions via keyboard shortcut.
 * Ctrl+K opens, type to filter, Enter to execute.
 */
import React, { useState, useCallback, useEffect } from "react";

interface Command {
  id: string;
  label: string;
  shortcut: string;
  category: string;
  action: () => void;
}

const COMMANDS: Command[] = [
  { id: "nav_performance", label: "Go to Performance", shortcut: "Ctrl+1", category: "navigation", action: () => {} },
  { id: "nav_signals", label: "Go to Signals", shortcut: "Ctrl+2", category: "navigation", action: () => {} },
  { id: "nav_regimes", label: "Go to Regimes", shortcut: "Ctrl+3", category: "navigation", action: () => {} },
  { id: "nav_archetypes", label: "Go to Archetypes", shortcut: "Ctrl+4", category: "navigation", action: () => {} },
  { id: "action_pause", label: "Pause Trading", shortcut: "Ctrl+Shift+P", category: "execution", action: () => {} },
  { id: "action_resume", label: "Resume Trading", shortcut: "Ctrl+Shift+R", category: "execution", action: () => {} },
  { id: "action_kill", label: "Kill Switch", shortcut: "Ctrl+Shift+K", category: "governance", action: () => {} },
  { id: "action_replay", label: "Start Replay", shortcut: "Ctrl+Shift+L", category: "simulation", action: () => {} },
  { id: "view_compact", label: "Compact Density", shortcut: "", category: "view", action: () => {} },
  { id: "view_comfortable", label: "Comfortable Density", shortcut: "", category: "view", action: () => {} },
  { id: "view_fullscreen", label: "Toggle Fullscreen", shortcut: "F11", category: "view", action: () => {} },
  { id: "theme_dark", label: "Dark Theme", shortcut: "", category: "theme", action: () => {} },
  { id: "theme_light", label: "Light Theme", shortcut: "", category: "theme", action: () => {} },
];

export const CommandPalette: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = COMMANDS.filter(
    (c) =>
      c.label.toLowerCase().includes(query.toLowerCase()) ||
      c.category.toLowerCase().includes(query.toLowerCase())
  );

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.ctrlKey && e.key === "k") {
      e.preventDefault();
      setOpen((prev) => !prev);
      setQuery("");
    }
    if (e.key === "Escape") setOpen(false);
  }, []);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/50">
      <div className="w-[600px] bg-gray-900 rounded-lg shadow-2xl border border-gray-700">
        <input
          autoFocus
          className="w-full px-4 py-3 bg-transparent text-white text-lg outline-none border-b border-gray-700"
          placeholder="Type a command..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="max-h-80 overflow-y-auto">
          {filtered.map((cmd) => (
            <div
              key={cmd.id}
              className="px-4 py-2 hover:bg-gray-800 cursor-pointer flex justify-between items-center"
              onClick={() => { cmd.action(); setOpen(false); }}
            >
              <div>
                <span className="text-white">{cmd.label}</span>
                <span className="ml-2 text-xs text-gray-500">{cmd.category}</span>
              </div>
              {cmd.shortcut && (
                <span className="text-xs text-gray-400 font-mono">{cmd.shortcut}</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CommandPalette;
