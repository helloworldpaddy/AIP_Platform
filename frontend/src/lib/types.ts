// Mirrors backend/aml/models — keep in sync with the Pydantic state models.

export type CaseStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "AWAITING_REVIEW"
  | "ESCALATED"
  | "SUBMITTED"
  | "CLOSED";

export type CaseStage =
  | "INTAKE"
  | "INITIAL_ASSESSMENT"
  | "TRANSACTION_ENRICHMENT"
  | "DUE_DILIGENCE"
  | "CASE_ANALYSIS"
  | "COMPLETED";

export type CasePriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type AgentName =
  | "INITIAL_ASSESSMENT"
  | "TRANSACTION_ENRICHMENT"
  | "DUE_DILIGENCE"
  | "CASE_ANALYSIS";

export type AgentRunStatus =
  | "PENDING"
  | "RUNNING"
  | "AWAITING_REVIEW"
  | "APPROVED"
  | "MODIFIED"
  | "REJECTED"
  | "FAILED"
  | "COMPLETED";

export type EvidenceType =
  | "KYC_RECORD"
  | "TRANSACTION"
  | "GRAPH_RELATION"
  | "EXTERNAL_SEARCH"
  | "POLICY_RULE"
  | "SANCTIONS_HIT"
  | "ADVERSE_MEDIA"
  | "INTERNAL_NOTE";

export type Classification = "FALSE_POSITIVE" | "ESCALATE" | "SAR";

export type GateStatus = "OPEN_REQUIRED" | "APPROVED" | "REJECTED";

export type ActorType = "AGENT" | "ANALYST" | "SYSTEM";

export type AuditEventType =
  | "CASE_CREATED"
  | "CASE_STATUS_CHANGED"
  | "CASE_STAGE_ADVANCED"
  | "AGENT_STARTED"
  | "AGENT_REASONING"
  | "AGENT_COMPLETED"
  | "AGENT_FAILED"
  | "AGENT_RETRIED"
  | "EVIDENCE_RECORDED"
  | "GATE_OPENED"
  | "GATE_APPROVED"
  | "GATE_REJECTED"
  | "HUMAN_OVERRIDE"
  | "NARRATIVE_DRAFTED"
  | "NARRATIVE_SUBMITTED"
  | "RECORD_LOCKED";

export type PartyType = "INDIVIDUAL" | "CORPORATE" | "TRUST" | "OTHER";

export interface Case {
  id: string;
  case_number: string;
  alert_type: string;
  alert_payload: Record<string, unknown>;
  subject_party_id: string;
  subject_party_name: string;
  status: CaseStatus;
  current_stage: CaseStage;
  priority: CasePriority;
  assigned_analyst_id: string | null;
  locked: boolean;
  locked_at: string | null;
  locked_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string | null;
}

export interface TokenUsage {
  prompt: number;
  completion: number;
  total: number;
}

export interface AgentRun {
  id: string;
  case_id: string;
  agent: AgentName;
  attempt: number;
  idempotency_key: string;
  status: AgentRunStatus;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  reasoning: string | null;
  reasoning_summary: string | null;
  error: string | null;
  model_name: string | null;
  tokens: TokenUsage | null;
  duration_ms: number | null;
  human_modified: boolean;
  human_modified_at: string | null;
  human_modified_by: string | null;
  human_diff: Array<Record<string, unknown>> | null;
  approved_at: string | null;
  approved_by: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  id: string;
  case_id: string;
  agent_run_id: string | null;
  evidence_type: EvidenceType;
  source_system: string;
  source_uri: string | null;
  title: string;
  content: string;
  structured_data: Record<string, unknown>;
  content_hash: string;
  confidence_score: number | null;
  contains_pii: boolean;
  retrieved_at: string;
  created_by: string;
}

export interface Citation {
  footnote: number;
  evidence_id: string;
  excerpt: string | null;
}

export interface CaseParty {
  id: string;
  case_id: string;
  party_external_id: string;
  party_name: string;
  party_type: PartyType;
  relationship: string | null;
  hop_distance: number;
  risk_indicators: Record<string, unknown>;
  source_evidence_ids: string[];
  verified: boolean;
  verified_at: string | null;
  verified_by: string | null;
  created_at: string;
}

export interface HumanGate {
  id: string;
  case_id: string;
  gate_name: string;
  blocks_agent: AgentName;
  status: GateStatus;
  opened_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  notes: string | null;
}

export interface Narrative {
  id: string;
  case_id: string;
  version: number;
  classification: Classification;
  rationale: string;
  markdown_body: string;
  citations: Citation[];
  submitted: boolean;
  submitted_at: string | null;
  submitted_by: string | null;
  locked: boolean;
  human_modified: boolean;
  created_at: string;
  created_by: string;
}

export interface AuditEvent {
  id: number;
  case_id: string;
  agent_run_id: string | null;
  actor_type: ActorType;
  actor_id: string;
  event_type: AuditEventType;
  event_payload: Record<string, unknown>;
  reasoning_text: string | null;
  prev_hash: string | null;
  data_hash: string;
  created_at: string;
}

export interface StageProgress {
  stage: CaseStage;
  agent: AgentName;
  status: AgentRunStatus;
  latest_run_id: string | null;
  requires_review: boolean;
  blocking_gate: HumanGate | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface InvestigationState {
  case: Case;
  agent_runs: AgentRun[];
  evidence: Evidence[];
  parties: CaseParty[];
  gates: HumanGate[];
  narratives: Narrative[];
  progress: StageProgress[];
}

export interface CaseSummary {
  id: string;
  case_number: string;
  alert_type: string;
  status: CaseStatus;
  current_stage: CaseStage;
  priority: CasePriority;
  assigned_analyst_id: string | null;
  subject_party_name: string;
  created_at: string;
  updated_at: string;
  [k: string]: unknown;
}

export interface CaseCreate {
  case_number: string;
  alert_type: string;
  alert_payload: Record<string, unknown>;
  subject_party_id: string;
  subject_party_name: string;
  priority?: CasePriority;
  assigned_analyst_id?: string | null;
  created_by: string;
}

export interface AuditChainStatus {
  ok: boolean;
  first_bad_id: number | null;
}

export const AGENT_ORDER: AgentName[] = [
  "INITIAL_ASSESSMENT",
  "TRANSACTION_ENRICHMENT",
  "DUE_DILIGENCE",
  "CASE_ANALYSIS",
];

export const STAGE_FOR_AGENT: Record<AgentName, CaseStage> = {
  INITIAL_ASSESSMENT: "INITIAL_ASSESSMENT",
  TRANSACTION_ENRICHMENT: "TRANSACTION_ENRICHMENT",
  DUE_DILIGENCE: "DUE_DILIGENCE",
  CASE_ANALYSIS: "CASE_ANALYSIS",
};

// ---------------- Case graph (force-directed viz) ----------------

export interface GraphNode {
  id: string;
  label: string;
  kind: "subject" | "party" | "account" | "transaction";
  party_type: PartyType | null;
  hop_distance: number | null;
  verified: boolean | null;
  risk_indicators: Record<string, unknown>;
}

export interface GraphLink {
  source: string;
  target: string;
  relationship: string;
  weight: number;
  metadata: Record<string, unknown>;
}

export interface CaseGraphResponse {
  case_id: string;
  subject_party_id: string;
  nodes: GraphNode[];
  links: GraphLink[];
  source: "case_parties" | "neo4j" | "hybrid";
}

export const AGENT_LABEL: Record<AgentName, string> = {
  INITIAL_ASSESSMENT: "Initial Assessment",
  TRANSACTION_ENRICHMENT: "Transaction Enrichment",
  DUE_DILIGENCE: "Due Diligence",
  CASE_ANALYSIS: "Case Analysis",
};
