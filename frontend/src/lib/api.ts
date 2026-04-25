import { getAnalystId } from "@/lib/analyst";
import type {
  AgentName,
  AgentRun,
  AuditChainStatus,
  AuditEvent,
  Case,
  CaseCreate,
  CaseGraphResponse,
  CaseParty,
  CasePriority,
  CaseStatus,
  CaseSummary,
  GateStatus,
  HumanGate,
  InvestigationState,
  Narrative,
} from "@/lib/types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { analyst?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // Attach analyst header on every call — backend rejects mutating routes
  // without it, and read-only routes simply ignore it.
  const analystId = getAnalystId();
  if (analystId) headers.set("X-Analyst-Id", analystId);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let body: unknown = null;
    let text = "";
    try {
      text = await res.text();
      body = text ? JSON.parse(text) : null;
    } catch {
      body = text;
    }
    const detail =
      (body as { detail?: string } | null)?.detail ?? text ?? res.statusText;
    throw new ApiError(res.status, detail || `HTTP ${res.status}`, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------- Cases ----------------

export const casesApi = {
  list: (params: { status?: CaseStatus; assigned?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.assigned) qs.set("assigned_analyst_id", params.assigned);
    const q = qs.toString();
    return request<CaseSummary[]>(`/cases${q ? `?${q}` : ""}`);
  },
  get: (caseId: string) => request<InvestigationState>(`/cases/${caseId}`),
  create: (body: CaseCreate) =>
    request<Case>("/cases", { method: "POST", body: JSON.stringify(body) }),
  assign: (caseId: string, analystId: string | null) =>
    request<Case>(`/cases/${caseId}/assign`, {
      method: "POST",
      body: JSON.stringify({ analyst_id: analystId }),
    }),
  setPriority: (caseId: string, priority: CasePriority) =>
    request<Case>(`/cases/${caseId}/priority`, {
      method: "PATCH",
      body: JSON.stringify({ priority }),
    }),
};

// ---------------- Agents ----------------

export const agentsApi = {
  trigger: (caseId: string, agent: AgentName, extra: Record<string, unknown> = {}) =>
    request<AgentRun>(`/cases/${caseId}/agents/${agent}/trigger`, {
      method: "POST",
      body: JSON.stringify({ extra_input: extra }),
    }),
  getRun: (runId: string) => request<AgentRun>(`/agents/runs/${runId}`),
  approve: (runId: string) =>
    request<AgentRun>(`/agents/runs/${runId}/approve`, { method: "POST" }),
  reject: (runId: string, reason: string) =>
    request<AgentRun>(`/agents/runs/${runId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  override: (
    runId: string,
    newOutput: Record<string, unknown>,
    diffOps: Array<Record<string, unknown>> = [],
  ) =>
    request<AgentRun>(`/agents/runs/${runId}/override`, {
      method: "POST",
      body: JSON.stringify({ new_output: newOutput, diff_ops: diffOps }),
    }),
};

// ---------------- Gates / Parties / Narratives / Audit ----------------

export const gatesApi = {
  resolve: (gateId: string, status: GateStatus, notes?: string) =>
    request<HumanGate>(`/gates/${gateId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ status, notes: notes ?? null }),
    }),
};

export const partiesApi = {
  verify: (partyId: string) =>
    request<CaseParty>(`/parties/${partyId}/verify`, { method: "POST" }),
};

export const narrativesApi = {
  update: (
    narrativeId: string,
    body: {
      rationale?: string | null;
      markdown_body?: string | null;
      citations?: Array<Record<string, unknown>> | null;
    },
  ) =>
    request<Narrative>(`/narratives/${narrativeId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  submit: (narrativeId: string) =>
    request<Narrative>(`/narratives/${narrativeId}/submit`, { method: "POST" }),
};

export const auditApi = {
  list: (caseId: string, limit = 200) =>
    request<AuditEvent[]>(`/cases/${caseId}/audit?limit=${limit}`),
  verify: (caseId: string) =>
    request<AuditChainStatus>(`/cases/${caseId}/audit/verify`),
};

export const graphApi = {
  get: (
    caseId: string,
    opts: { includeNeo4j?: boolean; hop?: number; windowDays?: number } = {},
  ) => {
    const qs = new URLSearchParams();
    if (opts.includeNeo4j) qs.set("include_neo4j", "true");
    if (opts.hop) qs.set("neo4j_hop", String(opts.hop));
    if (opts.windowDays) qs.set("neo4j_window_days", String(opts.windowDays));
    const q = qs.toString();
    return request<CaseGraphResponse>(`/cases/${caseId}/graph${q ? `?${q}` : ""}`);
  },
};

export const metaApi = {
  health: () => request<{ status: string; db: string }>("/healthz"),
};
