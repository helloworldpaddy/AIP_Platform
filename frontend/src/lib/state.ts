import type { AgentName, InvestigationState } from "@/lib/types";

export function isBlocked(state: InvestigationState, agent: AgentName): boolean {
  return state.gates.some(
    (g) => g.blocks_agent === agent && g.status === "OPEN_REQUIRED",
  );
}

export function latestRun(state: InvestigationState, agent: AgentName) {
  const runs = state.agent_runs.filter((r) => r.agent === agent);
  if (runs.length === 0) return null;
  return runs.reduce((acc, r) => (r.attempt > acc.attempt ? r : acc));
}

export function openGates(state: InvestigationState) {
  return state.gates.filter((g) => g.status === "OPEN_REQUIRED");
}

export function submittedNarrative(state: InvestigationState) {
  return state.narratives.find((n) => n.submitted) ?? null;
}

export function currentDraftNarrative(state: InvestigationState) {
  return [...state.narratives]
    .sort((a, b) => b.version - a.version)
    .find((n) => !n.submitted) ?? null;
}
