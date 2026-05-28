import type { ReactNode } from "react";

import { useWidgetVisible } from "@/state/widgetVisibility";

interface WidgetSlotProps {
  widgetKey: string;
  className?: string;
  children: ReactNode;
}

/**
 * Conditionally renders its children based on the per-widget visibility
 * setting managed by the widget-visibility store. When hidden it returns
 * null, removing the element from the DOM and collapsing the grid slot.
 *
 * When `className` is provided the children are wrapped in a `<div>` with
 * that class (preserving the grid-column and min-height constraints that
 * page layouts apply). When omitted the children are rendered bare inside
 * a fragment, which is appropriate for pages whose cards are direct flex /
 * block children (e.g. OperatorPage's space-y layout).
 */
export function WidgetSlot({ widgetKey, className, children }: WidgetSlotProps) {
  const visible = useWidgetVisible(widgetKey);
  if (!visible) return null;
  if (className) return <div className={className}>{children}</div>;
  return <>{children}</>;
}
