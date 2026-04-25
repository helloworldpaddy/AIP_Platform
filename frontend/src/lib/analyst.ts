// Analyst identity is held in localStorage and emitted via a window event so
// React can re-render when the user changes who they are acting as.

const KEY = "aml.analystId";
const EVENT = "aml.analystId.changed";

export function getAnalystId(): string {
  return (typeof window === "undefined" ? "" : localStorage.getItem(KEY)) ?? "";
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
