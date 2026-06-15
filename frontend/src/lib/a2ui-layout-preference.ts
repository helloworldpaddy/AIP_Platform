/** Assistant-mode A2UI presentation preference (Standard mode ignores this). */

export type A2uiLayoutId = "agent" | "executive" | "analyst" | "detailed";

const KEY = "aml.a2ui_layout_preference";
const CHANGED = "aml.a2ui_layout_preference.changed";

export const A2UI_LAYOUT_OPTIONS: Array<{
  id: A2uiLayoutId;
  label: string;
  description: string;
}> = [
  {
    id: "analyst",
    label: "Analyst tabs",
    description: "Summary, open questions, and actions in separate tabs.",
  },
  {
    id: "executive",
    label: "Executive brief",
    description: "Risk band, leading hypothesis, and approve only.",
  },
  {
    id: "detailed",
    label: "Detailed list",
    description: "All structured fields as a scannable list.",
  },
  {
    id: "agent",
    label: "Agent layout",
    description: "Use the layout emitted by the stage agent (when available).",
  },
];

export function getA2uiLayoutPreference(): A2uiLayoutId {
  if (typeof window === "undefined") return "analyst";
  const raw = localStorage.getItem(KEY);
  if (raw === "agent" || raw === "executive" || raw === "analyst" || raw === "detailed") {
    return raw;
  }
  return "analyst";
}

export function setA2uiLayoutPreference(layout: A2uiLayoutId): void {
  localStorage.setItem(KEY, layout);
  window.dispatchEvent(new CustomEvent(CHANGED, { detail: layout }));
}

export function subscribeA2uiLayoutPreference(cb: () => void): () => void {
  window.addEventListener(CHANGED, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED, cb);
    window.removeEventListener("storage", cb);
  };
}

export function layoutLabel(layout: A2uiLayoutId): string {
  return A2UI_LAYOUT_OPTIONS.find((o) => o.id === layout)?.label ?? layout;
}
