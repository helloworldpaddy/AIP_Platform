import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { casesApi } from "@/lib/api";
import type { CaseStatus } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Empty } from "@/components/ui/empty";
import { CaseStatusBadge, PriorityBadge } from "@/components/StatusBadge";
import { CreateCaseDialog } from "@/components/CreateCaseDialog";
import { formatRelative } from "@/lib/format";
import { Plus, FileSearch } from "lucide-react";

const STATUSES: (CaseStatus | "")[] = [
  "",
  "OPEN",
  "IN_PROGRESS",
  "AWAITING_REVIEW",
  "ESCALATED",
  "SUBMITTED",
  "CLOSED",
];

export function CasesPage() {
  const [status, setStatus] = useState<CaseStatus | "">("");
  const [createOpen, setCreateOpen] = useState(false);
  const cases = useQuery({
    queryKey: ["cases", status],
    queryFn: () => casesApi.list(status ? { status } : {}),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cases</h1>
          <p className="text-sm text-muted-foreground">
            All AML investigations across the four-stage agent workflow.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value as CaseStatus | "")}
            className="w-44"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s ? s.replace("_", " ") : "All statuses"}
              </option>
            ))}
          </Select>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New case
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Open work</CardTitle>
        </CardHeader>
        <CardContent>
          {cases.isLoading ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : cases.error ? (
            <div className="text-sm text-destructive">
              Failed to load: {(cases.error as Error).message}
            </div>
          ) : !cases.data || cases.data.length === 0 ? (
            <Empty
              title="No cases yet"
              description="Create one or wait for the alert intake job to land."
              action={
                <Button size="sm" className="mt-2" onClick={() => setCreateOpen(true)}>
                  <Plus className="h-4 w-4" /> New case
                </Button>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {cases.data.map((c) => (
                <li key={c.id} className="py-3">
                  <Link
                    to={`/cases/${c.id}`}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-md p-2 hover:bg-accent"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <FileSearch className="h-4 w-4 text-muted-foreground" />
                        <span className="font-mono text-sm font-medium">
                          {c.case_number}
                        </span>
                        <CaseStatusBadge status={c.status} />
                        <PriorityBadge priority={c.priority} />
                      </div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">
                        {c.subject_party_name} ·{" "}
                        {(c.line_of_business ?? "RETAIL_BANKING").replace(/_/g, " ").toLowerCase()} ·{" "}
                        {c.alert_type} · {c.assigned_analyst_id ?? "unassigned"}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                      <span>stage: {c.current_stage.replace(/_/g, " ").toLowerCase()}</span>
                      <span>updated {formatRelative(c.updated_at)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <CreateCaseDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
