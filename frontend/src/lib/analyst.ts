// Analyst identity is held in localStorage and emitted via a window event so
// React can re-render when the user changes who they are acting as.

const KEY = "aml.analystId";
const EVENT = "aml.analystId.changed";
const DEFAULT_ANALYST_ID = "analyst.demo";

export function getAnalystId(): string {
  if (typeof window === "undefined") return "";
  const v = localStorage.getItem(KEY);
  return (v && v.trim()) || DEFAULT_ANALYST_ID;
}

export function setAnalystId(id: string): void {
  localStorage.setItem(KEY, id);
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function subscribeAnalystId(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
