/**
 * Structured A2UI action dispatch (sketch).
 * Known actions hit REST directly; unknown actions fall back to aml-host chat.
 */

import { agentsApi, gatesApi, partiesApi } from "@/lib/api";
import {
  actionToUserMessage,
  type ActionPayload,
} from "@/lib/a2ui-render";
import type { AgentName, GateStatus } from "@/lib/types";

export type A2uiActionContext = {
  caseId: string;
  caseNumber: string;
  invalidateCase: () => void;
  onChatFallback: (message: string) => void;
  onSuccess?: (message: string) => void;
  onError?: (message: string) => void;
};

function str(ctx: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const v = ctx[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return undefined;
}

function agentName(raw: string): AgentName | undefined {
  const token = raw.trim().toUpperCase();
  const names: AgentName[] = [
    "INITIAL_ASSESSMENT",
    "TRANSACTION_ENRICHMENT",
    "DUE_DILIGENCE",
    "CASE_ANALYSIS",
  ];
  return names.find((n) => n === token);
}

function gateStatus(raw: string): GateStatus | undefined {
  const token = raw.trim().toUpperCase();
  if (token === "APPROVED" || token === "REJECTED" || token === "OPEN_REQUIRED") {
    return token;
  }
  return undefined;
}

/**
 * Route an A2UI button action. Returns true when handled without chat fallback.
 */
export async function dispatchA2uiAction(
  action: ActionPayload,
  ctx: A2uiActionContext,
): Promise<boolean> {
  const c = action.context ?? {};
  const name = action.name.trim().toLowerCase();

  try {
    switch (name) {
      case "approve_run":
      case "approve_agent_run": {
        const runId = str(c, "runId", "run_id", "id");
        if (!runId) break;
        await agentsApi.approve(runId);
        ctx.invalidateCase();
        ctx.onSuccess?.("Run approved.");
        return true;
      }

      case "reject_run":
      case "reject_agent_run": {
        const runId = str(c, "runId", "run_id", "id");
        const reason = str(c, "reason", "notes") ?? "Rejected from Agent UI";
        if (!runId) break;
        await agentsApi.reject(runId, reason);
        ctx.invalidateCase();
        ctx.onSuccess?.("Run rejected.");
        return true;
      }

      case "verify_party": {
        const partyId = str(c, "partyId", "party_id", "id");
        if (!partyId) break;
        await partiesApi.verify(partyId);
        ctx.invalidateCase();
        ctx.onSuccess?.("Party verified.");
        return true;
      }

      case "resolve_gate":
      case "approve_gate": {
        const gateId = str(c, "gateId", "gate_id", "id");
        const status =
          gateStatus(str(c, "status", "resolution") ?? "APPROVED") ?? "APPROVED";
        if (!gateId) break;
        await gatesApi.resolve(
          gateId,
          status,
          str(c, "notes", "reason"),
        );
        ctx.invalidateCase();
        ctx.onSuccess?.(`Gate ${status.toLowerCase()}.`);
        return true;
      }

      case "run_stage":
      case "trigger_stage":
      case "trigger_workflow_stage": {
        const stage = str(c, "stage", "agent", "agentName", "agent_name");
        if (!stage) break;
        const agent = agentName(stage);
        if (!agent) break;
        await agentsApi.trigger(ctx.caseId, agent);
        ctx.invalidateCase();
        ctx.onSuccess?.(`Triggered ${agent}.`);
        return true;
      }

      default:
        break;
    }
  } catch (err) {
    ctx.onError?.((err as Error).message);
    return true;
  }

  ctx.onChatFallback(actionToUserMessage(action, ctx.caseNumber));
  return false;
}
