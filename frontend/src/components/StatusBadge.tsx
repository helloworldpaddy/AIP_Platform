import { Badge } from "@/components/ui/badge";
import type {
  AgentRunStatus,
  CasePriority,
  CaseStatus,
  GateStatus,
  Classification,
} from "@/lib/types";

const RUN: Record<AgentRunStatus, { variant: Parameters<typeof Badge>[0]["variant"]; label: string }> = {
  PENDING: { variant: "outline", label: "Pending" },
  RUNNING: { variant: "info", label: "Running" },
  AWAITING_REVIEW: { variant: "warning", label: "Review Required" },
  APPROVED: { variant: "success", label: "Approved" },
  MODIFIED: { variant: "success", label: "Modified" },
  REJECTED: { variant: "destructive", label: "Rejected" },
  FAILED: { variant: "destructive", label: "Failed" },
  COMPLETED: { variant: "success", label: "Completed" },
};

export function RunStatusBadge({ status }: { status: AgentRunStatus }) {
  const cfg = RUN[status];
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

const CASE: Record<CaseStatus, { variant: Parameters<typeof Badge>[0]["variant"]; label: string }> = {
  OPEN: { variant: "info", label: "Open" },
  IN_PROGRESS: { variant: "info", label: "In Progress" },
  AWAITING_REVIEW: { variant: "warning", label: "Awaiting Review" },
  ESCALATED: { variant: "destructive", label: "Escalated" },
  SUBMITTED: { variant: "success", label: "Submitted" },
  CLOSED: { variant: "secondary", label: "Closed" },
};

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  const cfg = CASE[status];
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

const PRIORITY: Record<CasePriority, Parameters<typeof Badge>[0]["variant"]> = {
  LOW: "secondary",
  MEDIUM: "info",
  HIGH: "warning",
  CRITICAL: "destructive",
};

export function PriorityBadge({ priority }: { priority: CasePriority }) {
  return <Badge variant={PRIORITY[priority]}>{priority}</Badge>;
}

const GATE: Record<GateStatus, { variant: Parameters<typeof Badge>[0]["variant"]; label: string }> = {
  OPEN_REQUIRED: { variant: "warning", label: "Open" },
  APPROVED: { variant: "success", label: "Approved" },
  REJECTED: { variant: "destructive", label: "Rejected" },
};

export function GateStatusBadge({ status }: { status: GateStatus }) {
  const cfg = GATE[status];
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

const CLASS: Record<Classification, Parameters<typeof Badge>[0]["variant"]> = {
  FALSE_POSITIVE: "success",
  ESCALATE: "warning",
  SAR: "destructive",
};

export function ClassificationBadge({ value }: { value: Classification }) {
  return <Badge variant={CLASS[value]}>{value}</Badge>;
}
