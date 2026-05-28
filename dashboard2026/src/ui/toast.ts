/**
 * Toast notification utility.
 *
 * Minimal implementation for operator feedback.
 */

export type ToastLevel = "info" | "success" | "warning" | "error";

export interface ToastOptions {
  tone?: ToastLevel;
  ttl_ms?: number;
}

interface Toast {
  id: number;
  message: string;
  level: ToastLevel;
}

let nextId = 0;
const listeners: Array<(toasts: Toast[]) => void> = [];
let toasts: Toast[] = [];

function notify() {
  listeners.forEach((fn) => fn([...toasts]));
}

export function pushToast(message: string, levelOrOpts?: ToastLevel | ToastOptions) {
  let level: ToastLevel = "info";
  let ttl = 5000;

  if (typeof levelOrOpts === "string") {
    level = levelOrOpts;
  } else if (levelOrOpts) {
    level = levelOrOpts.tone ?? "info";
    ttl = levelOrOpts.ttl_ms ?? 5000;
  }

  const toast: Toast = { id: nextId++, message, level };
  toasts = [...toasts, toast];
  notify();

  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== toast.id);
    notify();
  }, ttl);
}

export function subscribe(fn: (toasts: Toast[]) => void) {
  listeners.push(fn);
  return () => {
    const idx = listeners.indexOf(fn);
    if (idx >= 0) listeners.splice(idx, 1);
  };
}

export function getToasts(): Toast[] {
  return [...toasts];
}
