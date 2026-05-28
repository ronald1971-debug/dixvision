import { X } from "lucide-react";
import { useState } from "react";

import {
  WIDGET_REGISTRY,
  isWidgetVisible,
  resetAllVisible,
  setPageAllVisible,
  setWidgetPanelOpen,
  setWidgetVisible,
  useWidgetPanelOpen,
  useWidgetVisibilitySnapshot,
  type PageDef,
} from "@/state/widgetVisibility";

// ── Toggle switch ──────────────────────────────────────────────────────────────

function ToggleSwitch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center rounded-full border transition-colors ${
        checked
          ? "border-accent bg-accent/25"
          : "border-slate-600 bg-slate-800"
      }`}
    >
      <span
        className={`absolute h-[11px] w-[11px] rounded-full transition-transform ${
          checked
            ? "translate-x-[13px] bg-accent"
            : "translate-x-[1px] bg-slate-500"
        }`}
      />
    </button>
  );
}

// ── Section (one per page) ────────────────────────────────────────────────────

function PageSection({
  page,
  snap,
}: {
  page: PageDef;
  snap: Record<string, boolean>;
}) {
  const [expanded, setExpanded] = useState(true);
  const allVisible = page.widgets.every((w) => isWidgetVisible(w.key, snap));
  const noneVisible = page.widgets.every((w) => !isWidgetVisible(w.key, snap));

  return (
    <div className="border-t border-border">
      {/* Section header */}
      <div className="flex items-center gap-1 px-3 py-1.5">
        <button
          type="button"
          className="flex flex-1 items-center gap-1 text-left"
          onClick={() => setExpanded((e) => !e)}
        >
          <span
            className={`font-mono text-[9px] transition-transform ${
              expanded ? "rotate-90" : "rotate-0"
            }`}
          >
            ▶
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
            {page.label}
          </span>
          <span className="ml-1 font-mono text-[9px] text-slate-600">
            {page.widgets.filter((w) => isWidgetVisible(w.key, snap)).length}/
            {page.widgets.length}
          </span>
        </button>
        <button
          type="button"
          onClick={() => setPageAllVisible(page.id, true)}
          disabled={allVisible}
          className="px-1 font-mono text-[9px] text-slate-500 hover:text-slate-200 disabled:opacity-30"
          title="Show all"
        >
          all
        </button>
        <span className="text-slate-700">·</span>
        <button
          type="button"
          onClick={() => setPageAllVisible(page.id, false)}
          disabled={noneVisible}
          className="px-1 font-mono text-[9px] text-slate-500 hover:text-slate-200 disabled:opacity-30"
          title="Hide all"
        >
          none
        </button>
      </div>

      {/* Widget rows */}
      {expanded && (
        <ul className="pb-1">
          {page.widgets.map((w) => {
            const visible = isWidgetVisible(w.key, snap);
            return (
              <li
                key={w.key}
                className="flex items-center justify-between px-4 py-[5px] hover:bg-slate-800/50"
              >
                <span
                  className={`text-[11px] transition-colors ${
                    visible ? "text-slate-200" : "text-slate-600"
                  }`}
                >
                  {w.label}
                </span>
                <ToggleSwitch
                  checked={visible}
                  onChange={(v) => setWidgetVisible(w.key, v)}
                  label={`Toggle ${w.label}`}
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

const GROUPS = ["System", "Analysis", "Trading", "Assets"] as const;

export function WidgetTogglePanel() {
  const open = useWidgetPanelOpen();
  const snap = useWidgetVisibilitySnapshot();

  // Group pages by their group field
  const grouped = GROUPS.map((g) => ({
    group: g,
    pages: WIDGET_REGISTRY.filter((p) => p.group === g),
  }));

  return (
    <>
      {/* Backdrop (non-modal: pointer-events only on the panel itself) */}
      <div
        className={`fixed inset-y-0 right-0 z-40 flex flex-col border-l border-border bg-surface shadow-2xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ width: 300 }}
        aria-label="Widget visibility panel"
        role="dialog"
        aria-hidden={!open}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            Widget visibility
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={resetAllVisible}
              className="font-mono text-[9px] text-slate-600 hover:text-slate-300"
              title="Reset all to visible"
            >
              reset all
            </button>
            <button
              type="button"
              onClick={() => setWidgetPanelOpen(false)}
              className="rounded p-0.5 text-slate-500 hover:bg-slate-700 hover:text-slate-200"
              aria-label="Close panel"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          {grouped.map(({ group, pages }) => (
            <div key={group}>
              <div className="bg-bg/60 px-3 py-1 font-mono text-[9px] uppercase tracking-widest text-slate-600">
                {group}
              </div>
              {pages.map((page) => (
                <PageSection key={page.id} page={page} snap={snap} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
