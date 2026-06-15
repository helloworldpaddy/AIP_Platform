/**
 * Normalized analyst content extracted from an agent run (Assistant A2UI templates).
 */

import type { AgentRun } from "@/lib/types";

export type AnalystLine = { label: string; value: string };

export type CounterpartySalvage = {
  name: string;
  hop?: number;
  relationship?: string;
};

export type RunSurfaceContent = {
  agent: string;
  agentLabel: string;
  runId: string;
  status: string;
  lines: AnalystLine[];
  riskBand?: string;
  hypothesis?: string;
  summary?: string;
  partyCount?: number;
  counterparties: CounterpartySalvage[];
  questions: string[];
  redFlags: string[];
  extras: AnalystLine[];
  parseIncomplete: boolean;
  parsePartial: boolean;
  inferredRiskBand: boolean;
  inferredHypothesis: boolean;
  salvagedTe: boolean;
};

export function extractRunSurfaceContent(run: AgentRun): RunSurfaceContent {
  const payload = (run.output_payload ?? {}) as Record<string, unknown>;
  const lines = analystLinesFromPayload(payload, run.reasoning, run.agent);

  let riskBand: string | undefined;
  let hypothesis: string | undefined;
  let summary: string | undefined;
  let partyCount: number | undefined;
  const counterparties: CounterpartySalvage[] = [];
  const questions: string[] = [];
  const redFlags: string[] = [];
  const extras: AnalystLine[] = [];

  for (const line of lines) {
    const lower = line.label.toLowerCase();
    if (lower === "risk band") {
      riskBand = line.value;
    } else if (lower === "leading hypothesis") {
      hypothesis = line.value;
    } else if (lower === "summary") {
      summary = line.value;
    } else if (lower === "parties discovered") {
      const n = Number(line.value);
      if (!Number.isNaN(n)) partyCount = n;
    } else if (lower.startsWith("open question")) {
      questions.push(line.value);
    } else if (lower.startsWith("red flag")) {
      redFlags.push(line.value);
    } else if (lower.startsWith("counterparty")) {
      counterparties.push(parseCounterpartyLine(line.value));
    } else if (lower === "summary" && !summary) {
      if (!isProceduralSummary(line.value)) {
        summary = line.value;
      }
    } else {
      extras.push(line);
    }
  }

  if (partyCount === undefined && counterparties.length > 0) {
    partyCount = counterparties.length;
  }

  const isTe = run.agent === "TRANSACTION_ENRICHMENT";
  const hasStructured = Boolean(
    isTe
      ? summary || counterparties.length > 0 || partyCount
      : riskBand || hypothesis || questions.length > 0 || redFlags.length > 0,
  );

  const parseFailed = payload.error === "failed_to_parse_output";

  return {
    agent: run.agent,
    agentLabel: run.agent.replace(/_/g, " "),
    runId: run.id,
    status: run.status,
    lines,
    riskBand,
    hypothesis,
    summary,
    partyCount,
    counterparties,
    questions,
    redFlags,
    extras,
    parseIncomplete: parseFailed && !hasStructured,
    parsePartial: parseFailed && hasStructured && (isTe ? !summary : !riskBand || !hypothesis),
    inferredRiskBand: payload._inferred_risk_band === true,
    inferredHypothesis: payload._inferred_hypothesis === true,
    salvagedTe: payload._salvaged_te === true,
  };
}

function analystLinesFromPayload(
  payload: Record<string, unknown>,
  reasoning?: string | null,
  agent?: string,
): AnalystLine[] {
  const structured = linesFromStructuredPayload(payload);
  if (structured.length > 0) return structured;

  if (payload.error === "failed_to_parse_output") {
    const combined = combineSalvageText(payload, reasoning);
    if (agent === "TRANSACTION_ENRICHMENT") {
      const te = parseTeSummaryFromText(combined);
      if (te.length > 0) return te;
    }
    const salvaged = parseIaSummaryFromText(combined);
    if (salvaged.length > 0) return salvaged;
  }

  if (reasoning && payload.error !== "failed_to_parse_output") {
    return [{ label: "Summary", value: truncateForDisplay(reasoning) }];
  }

  return [];
}

function linesFromStructuredPayload(payload: Record<string, unknown>): AnalystLine[] {
  const lines: AnalystLine[] = [];
  const preferred: Array<[string, string]> = [
    ["risk_band", "Risk band"],
    ["risk_score", "Risk score"],
    ["scenario_type", "Scenario type"],
    ["summary", "Summary"],
    ["hypothesis", "Leading hypothesis"],
    ["leading_hypothesis", "Leading hypothesis"],
    ["classification", "Classification"],
    ["party_count", "Parties discovered"],
  ];
  const seenLabels = new Set<string>();

  for (const [key, label] of preferred) {
    if (seenLabels.has(label)) continue;
    const val = payload[key];
    if (val === null || val === undefined) continue;
    if (typeof val === "string" || typeof val === "number" || typeof val === "boolean") {
      lines.push({ label, value: String(val) });
      seenLabels.add(label);
    }
  }

  const questions = payload.open_questions;
  if (Array.isArray(questions)) {
    questions.forEach((q, idx) => {
      if (typeof q === "string" && q.trim()) {
        lines.push({ label: `Open question ${idx + 1}`, value: q.trim() });
      }
    });
  }

  const redFlags = payload.red_flags;
  if (Array.isArray(redFlags)) {
    redFlags.forEach((flag, idx) => {
      if (typeof flag === "string" && flag.trim()) {
        lines.push({ label: `Red flag ${idx + 1}`, value: flag.trim() });
      }
    });
  }

  const parties = payload.parties;
  if (Array.isArray(parties)) {
    parties.forEach((party, idx) => {
      if (!party || typeof party !== "object") return;
      const rec = party as Record<string, unknown>;
      const name = rec.party_name;
      if (typeof name !== "string" || !name.trim()) return;
      const hop = rec.hop_distance;
      const rel = rec.relationship;
      let detail = name.trim();
      if (typeof hop === "number" || typeof hop === "string") {
        detail += ` (hop ${hop}`;
        if (typeof rel === "string" && rel.trim()) {
          detail += `, ${rel.trim()}`;
        }
        detail += ")";
      }
      lines.push({ label: `Counterparty ${idx + 1}`, value: detail });
    });
  }

  return lines;
}

function combineSalvageText(
  payload: Record<string, unknown>,
  reasoning?: string | null,
): string {
  const parts: string[] = [];
  const raw = payload.raw_text;
  if (typeof raw === "string" && raw.trim()) parts.push(raw.trim());
  if (reasoning?.trim()) parts.push(reasoning.trim());
  return parts.join("\n\n");
}

function parseTeSummaryFromText(text: string): AnalystLine[] {
  const lines: AnalystLine[] = [];
  const partyBlocks = text.matchAll(
    /Party\s+\d+:\s*\n(.*?)(?=\nParty\s+\d+:|\n\n(?:All parties|The summary|Now I will)|\Z)/gis,
  );

  const parties: CounterpartySalvage[] = [];
  for (const block of partyBlocks) {
    const chunk = block[1];
    const name = chunk.match(/party_name[`'"]?\s*:\s*"([^"]+)"/i);
    if (!name?.[1]) continue;
    const hop = chunk.match(/hop_distance[`'"]?\s*:\s*(\d+)/i);
    const rel = chunk.match(/relationship[`'"]?\s*:\s*"([^"]+)"/i);
    parties.push({
      name: name[1].trim(),
      hop: hop ? Number(hop[1]) : undefined,
      relationship: rel?.[1]?.trim(),
    });
  }

  const summaryMatch = text.match(
    /(?:The summary will reflect that )?(\d+)\s+counter-parties?\s+were found at hop-(\d+)/i,
  );
  if (summaryMatch) {
    lines.push({
      label: "Summary",
      value: `${summaryMatch[1]} counter-parties at hop-${summaryMatch[2]}; hop-2 added no new unique parties.`,
    });
  } else if (parties.length > 0) {
    const maxHop = Math.max(...parties.map((p) => p.hop ?? 1));
    lines.push({
      label: "Summary",
      value: `${parties.length} counter-parties identified at hop-${maxHop}.`,
    });
  }

  if (parties.length > 0) {
    lines.push({ label: "Parties discovered", value: String(parties.length) });
    parties.forEach((p, idx) => {
      let detail = p.name;
      if (p.hop !== undefined) {
        detail += ` (hop ${p.hop}`;
        if (p.relationship) detail += `, ${p.relationship}`;
        detail += ")";
      }
      lines.push({ label: `Counterparty ${idx + 1}`, value: detail });
    });
  }

  return lines;
}

function parseCounterpartyLine(value: string): CounterpartySalvage {
  const m = value.match(/^(.+?)\s*\(hop\s*(\d+)(?:,\s*([^)]+))?\)\s*$/i);
  if (m) {
    return {
      name: m[1].trim(),
      hop: Number(m[2]),
      relationship: m[3]?.trim(),
    };
  }
  return { name: value.trim() };
}

function parseIaSummaryFromText(text: string): AnalystLine[] {
  const lines: AnalystLine[] = [];
  const risk = text.match(/(?:\*\*)?Risk\s+Band:?(?:\*\*)?\s*([A-Z][A-Z_]+|\w+)/i);
  if (risk?.[1]) lines.push({ label: "Risk band", value: risk[1].toUpperCase() });

  const hypo = text.match(
    /(?:\*\*)?(?:Leading\s+)?Hypothesis:?(?:\*\*)?\s*([\s\S]+?)(?=(?:\*\*)?Open\s+Questions|\n\s*\d+\.\s|\Z)/i,
  );
  if (hypo?.[1]?.trim()) {
    lines.push({ label: "Leading hypothesis", value: cleanProse(hypo[1]) });
  }

  const oq = text.match(
    /(?:\*\*)?Open\s+Questions:?(?:\*\*)?\s*([\s\S]+?)(?=(?:\*\*)?(?:\d+\.\s*)?red\s+flags?|\Z)/i,
  );
  if (oq?.[1]) {
    parseNumberedLines(oq[1]).forEach((q, idx) => {
      lines.push({ label: `Open question ${idx + 1}`, value: q });
    });
  }

  const rf = text.match(
    /(?:\*\*\d+\.\s*)?(?:Surface\s+any\s+obvious\s+)?red\s+flags?:?(?:\*\*)?\s*([\s\S]+?)(?=(?:\n\s*\n(?:Now I will|I will now)|\Z))/i,
  );
  if (rf?.[1]) {
    parseBulletLines(rf[1]).forEach((flag, idx) => {
      lines.push({ label: `Red flag ${idx + 1}`, value: flag });
    });
  }

  return lines;
}

function isProceduralSummary(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    lower.includes("policy citations are now recorded") ||
    lower.includes("now i will construct") ||
    lower.includes("surface any obvious red flags")
  );
}

function cleanProse(text: string): string {
  return truncateForDisplay(text.trim().replace(/\n{3,}/g, "\n\n"));
}

function parseNumberedLines(block: string): string[] {
  const items: string[] = [];
  for (const raw of block.split("\n")) {
    const line = raw.trim().replace(/^\d+\.\s*/, "").replace(/^[-*]\s*/, "");
    if (line) items.push(line);
  }
  return items;
}

function parseBulletLines(block: string): string[] {
  const items: string[] = [];
  for (const raw of block.split("\n")) {
    let line = raw.trim().replace(/^[-*]\s*/, "");
    if (!line) continue;
    line = line.replace(/\*\*([^*]+)\*\*:?\s*/g, "$1: ");
    line = line.replace(/\*\*/g, "").trim().replace(/::/g, ":");
    if (line) items.push(line);
  }
  return items;
}

export function partialAssessmentNote(content: RunSurfaceContent): string | null {
  const isTe = content.agent === "TRANSACTION_ENRICHMENT";

  if (content.parseIncomplete) {
    return isTe
      ? "Structured output incomplete. Re-run enrichment or review counterparties in the case panel."
      : "Structured output incomplete. Re-run initial assessment or review evidence in the case panels.";
  }

  if (!content.parsePartial) return null;

  if (isTe) {
    const salvaged = content.salvagedTe
      ? " Counterparty list salvaged from agent reasoning."
      : "";
    return `Partial enrichment — agent output was cut off before final JSON.${salvaged} Re-run only if you need the full structured record.`;
  }

  const inferred =
    content.inferredRiskBand || content.inferredHypothesis
      ? " Risk band and hypothesis were inferred from salvaged red flags."
      : "";
  return `Partial assessment — agent output was cut off before final JSON.${inferred} Re-run only if you need the full structured record for sign-off.`;
}

export function truncateForDisplay(text: string, max = 320): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}

export function isLowQualityStoredA2ui(messages: Record<string, unknown>[]): boolean {
  const blob = JSON.stringify(messages).toLowerCase();
  return (
    blob.includes("failed_to_parse_output") ||
    blob.includes("expecting value") ||
    blob.includes("error: failed") ||
    blob.includes("policy citations are now recorded") ||
    blob.includes("risk band: not assessed") ||
    blob.includes("risk band and hypothesis may be missing")
  );
}
