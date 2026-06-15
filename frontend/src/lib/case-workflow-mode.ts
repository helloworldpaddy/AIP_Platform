/** Per-case workflow: conversational assistant vs classic run panel. */

export type CaseWorkflowMode = "assistant" | "standard";

const CASE_PREFIX = "aml.case_workflow_mode.";
const DEFAULT_KEY = "aml.case_workflow_default_mode";
const CHANGED_EVENT = "aml.case_workflow_mode.changed";

export function isAssistantChatAvailable(): boolean {
  return (
    (import.meta.env.VITE_AML_AGENT_CHAT_ENABLED as string | undefined)?.toLowerCase() !==
    "false"
  );
}

export function getCaseWorkflowMode(caseId: string): CaseWorkflowMode | null {
  if (typeof window === "undefined" || !caseId) return null;
  const raw = localStorage.getItem(`${CASE_PREFIX}${caseId}`);
  if (raw === "assistant" || raw === "standard") return raw;
  return null;
}

export function getDefaultWorkflowMode(): CaseWorkflowMode | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(DEFAULT_KEY);
  if (raw === "assistant" || raw === "standard") return raw;
  return null;
}

export function setCaseWorkflowMode(
  caseId: string,
  mode: CaseWorkflowMode,
  options?: { rememberAsDefault?: boolean },
): void {
  localStorage.setItem(`${CASE_PREFIX}${caseId}`, mode);
  if (options?.rememberAsDefault) {
    localStorage.setItem(DEFAULT_KEY, mode);
  }
  window.dispatchEvent(new CustomEvent(CHANGED_EVENT, { detail: { caseId, mode } }));
}

export function clearCaseWorkflowMode(caseId: string): void {
  localStorage.removeItem(`${CASE_PREFIX}${caseId}`);
  window.dispatchEvent(new CustomEvent(CHANGED_EVENT, { detail: { caseId, mode: null } }));
}

export function subscribeWorkflowMode(cb: () => void): () => void {
  window.addEventListener(CHANGED_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function workflowModeLabel(mode: CaseWorkflowMode): string {
  return mode === "assistant" ? "Assistant · Chat & A2UI" : "Standard · Run panel";
}

export function resolveInitialWorkflowMode(caseId: string): CaseWorkflowMode | null {
  const perCase = getCaseWorkflowMode(caseId);
  if (perCase) return perCase;
  const defaultMode = getDefaultWorkflowMode();
  if (defaultMode === "assistant" && !isAssistantChatAvailable()) {
    return "standard";
  }
  return defaultMode;
}
