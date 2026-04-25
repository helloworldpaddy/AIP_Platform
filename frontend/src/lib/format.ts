export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const abs = Math.abs(diff);
  const min = 60_000;
  const hr = 60 * min;
  const day = 24 * hr;
  const sign = diff >= 0 ? "ago" : "from now";
  if (abs < min) return `just now`;
  if (abs < hr) return `${Math.floor(abs / min)}m ${sign}`;
  if (abs < day) return `${Math.floor(abs / hr)}h ${sign}`;
  return `${Math.floor(abs / day)}d ${sign}`;
}

export function pretty(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
