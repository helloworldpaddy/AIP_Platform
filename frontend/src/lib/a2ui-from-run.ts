/**
 * Load A2UI surfaces from agent runs (Assistant mode).
 * Layout is user-selectable; Standard mode does not use this path.
 */

import type { A2uiMessage } from "@/lib/a2a";
import { applyA2uiMessages, type A2uiSurfaceState } from "@/lib/a2ui-render";
import type { A2uiLayoutId } from "@/lib/a2ui-layout-preference";
import { buildSurfaceMessagesForRun } from "@/lib/a2ui-layouts";
import type { AgentRun, AgentRunStatus } from "@/lib/types";

export function a2uiMessagesFromRuns(
  runs: AgentRun[],
  layout: A2uiLayoutId,
): A2uiMessage[] {
  const messages: A2uiMessage[] = [];
  for (const run of runs) {
    messages.push(...buildSurfaceMessagesForRun(run, layout));
  }
  return messages;
}

export function surfacesFromRuns(
  runs: AgentRun[],
  layout: A2uiLayoutId,
): Map<string, A2uiSurfaceState> {
  const messages = a2uiMessagesFromRuns(runs, layout);
  if (messages.length === 0) return new Map();
  return applyA2uiMessages(new Map(), messages);
}

/** Runs that should show an interactive surface (completed stages). */
export function runsWithSurfaces(runs: AgentRun[]): AgentRun[] {
  return runs.filter(
    (r) =>
      r.output_payload &&
      (r.status === "AWAITING_REVIEW" ||
        r.status === "APPROVED" ||
        r.status === "COMPLETED" ||
        r.status === "MODIFIED"),
  );
}

export function agentLabel(agent: string): string {
  return agent.replace(/_/g, " ");
}

export function statusLabel(status: AgentRunStatus): string {
  return status.replace(/_/g, " ").toLowerCase();
}
