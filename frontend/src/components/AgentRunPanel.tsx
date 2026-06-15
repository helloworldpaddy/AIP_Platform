import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi, ApiError } from "@/lib/api";
import { isBlocked, latestRun } from "@/lib/state";
import { AGENT_LABEL, type AgentName, type Citation, type InvestigationState } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Empty } from "@/components/ui/empty";
import { Badge } from "@/components/ui/badge";
import { CitationsList } from "@/components/CitationsList";
import { RunStatusBadge } from "@/components/StatusBadge";
import { formatTime, pretty } from "@/lib/format";
import { Lock, Play, ThumbsDown, ThumbsUp, Pencil, AlertTriangle } from "lucide-react";

interface Props {
  state: InvestigationState;
  agent: AgentName;
}

export function AgentRunPanel({ state, agent }: Props) {
  const qc = useQueryClient();
  const run = latestRun(state, agent);
  const blocked = isBlocked(state, agent);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [rejectReason, setRejectReason] = useState("");

  const refresh = () => qc.invalidateQueries({ queryKey: ["case", state.case.id] });

  const trigger = useMutation({
    mutationFn: () => agentsApi.trigger(state.case.id, agent),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: () => agentsApi.approve(run!.id),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: () => agentsApi.reject(run!.id, rejectReason.trim() || "rejected by analyst"),
    onSuccess: () => {
      setReasonOpen(false);
      setRejectReason("");
      refresh();
    },
  });
  const override = useMutation({
    mutationFn: () => {
      const parsed = JSON.parse(draft);
      return agentsApi.override(run!.id, parsed);
    },
    onSuccess: () => {
      setEditing(false);
      refresh();
    },
  });

  const citations: Citation[] = useMemo(() => {
    const raw = (run?.output_payload as { citations?: Citation[] } | null)?.citations;
    return Array.isArray(raw) ? raw : [];
  }, [run?.output_payload]);

  const startEdit = () => {
    setDraft(JSON.stringify(run?.output_payload ?? {}, null, 2));
    setEditing(true);
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-lg">{AGENT_LABEL[agent]}</CardTitle>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {run ? (
              <>
                <RunStatusBadge status={run.status} />
                <span>attempt #{run.attempt}</span>
                {run.model_name && (
                  <Badge variant="outline" className="font-mono normal-case">
                    {run.model_name}
                  </Badge>
                )}
                {run.tokens?.total ? <span>{run.tokens.total} tokens</span> : null}
                {run.duration_ms != null && <span>{run.duration_ms} ms</span>}
                {run.human_modified && <Badge variant="warning">Human-modified</Badge>}
              </>
            ) : (
              <span>No run yet for this stage.</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {blocked && (
            <Badge variant="warning" className="flex items-center gap-1">
              <Lock className="h-3 w-3" /> Gate blocking
            </Badge>
          )}
          <Button
            size="sm"
            variant="default"
            disabled={blocked || trigger.isPending || run?.status === "RUNNING"}
            onClick={() => trigger.mutate()}
          >
            <Play className="h-3.5 w-3.5" />
            {run ? "Re-run" : "Run"}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {trigger.error && <ErrorRow err={trigger.error} />}
        {approve.error && <ErrorRow err={approve.error} />}
        {reject.error && <ErrorRow err={reject.error} />}
        {override.error && <ErrorRow err={override.error} />}

        {!run ? (
          <Empty
            title="Agent has not run yet"
            description="Trigger this stage once any blocking gates are resolved."
          />
        ) : (
          <>
            {run.status === "AWAITING_REVIEW" && !editing && (
              <div className="flex flex-wrap gap-2 rounded-md border border-warning/40 bg-warning/5 p-3">
                <Button size="sm" variant="success" onClick={() => approve.mutate()} disabled={approve.isPending}>
                  <ThumbsUp className="h-3.5 w-3.5" /> Approve
                </Button>
                <Button size="sm" variant="outline" onClick={startEdit}>
                  <Pencil className="h-3.5 w-3.5" /> Edit output
                </Button>
                <Button size="sm" variant="destructive" onClick={() => setReasonOpen(true)}>
                  <ThumbsDown className="h-3.5 w-3.5" /> Reject
                </Button>
              </div>
            )}

            {reasonOpen && (
              <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Rejection reason
                </label>
                <Textarea
                  className="mt-1"
                  rows={3}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Explain why this output is being rejected…"
                />
                <div className="mt-2 flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setReasonOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={!rejectReason.trim() || reject.isPending}
                    onClick={() => reject.mutate()}
                  >
                    Confirm rejection
                  </Button>
                </div>
              </div>
            )}

            {editing && (
              <div className="rounded-md border border-primary/30 bg-primary/5 p-3">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Edited agent output (JSON)
                </label>
                <Textarea
                  className="mt-1 min-h-[260px] font-mono text-xs"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
                <div className="mt-2 flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="success"
                    disabled={override.isPending}
                    onClick={() => {
                      try {
                        JSON.parse(draft);
                      } catch (e) {
                        alert(`Invalid JSON: ${(e as Error).message}`);
                        return;
                      }
                      override.mutate();
                    }}
                  >
                    Save override + approve
                  </Button>
                </div>
              </div>
            )}

            <section>
              <SectionHeader title="Reasoning summary" />
              {run.reasoning_summary ? (
                <p className="text-sm text-muted-foreground">{run.reasoning_summary}</p>
              ) : (
                <p className="text-sm italic text-muted-foreground">Not provided.</p>
              )}
              {run.reasoning && (
                <button
                  type="button"
                  className="mt-2 text-xs font-medium text-primary hover:underline"
                  onClick={() => setShowReasoning((v) => !v)}
                >
                  {showReasoning ? "Hide full chain-of-thought" : "Show full chain-of-thought"}
                </button>
              )}
              {showReasoning && run.reasoning && (
                <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-3 text-xs">
                  {run.reasoning}
                </pre>
              )}
            </section>

            <section>
              <SectionHeader title="Output payload" />
              {run.output_payload ? (
                <pre className="max-h-80 overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">
                  {pretty(run.output_payload)}
                </pre>
              ) : (
                <p className="text-sm italic text-muted-foreground">No output recorded.</p>
              )}
            </section>

            {run.error && (
              <section>
                <SectionHeader title="Error" />
                <pre className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
                  {run.error}
                </pre>
              </section>
            )}

            <section>
              <SectionHeader title={`Citations (${citations.length})`} />
              <CitationsList citations={citations} evidence={state.evidence} />
            </section>

            <section className="text-xs text-muted-foreground">
              <SectionHeader title="Timing" />
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                <dt>Started</dt>
                <dd>{formatTime(run.started_at)}</dd>
                <dt>Completed</dt>
                <dd>{formatTime(run.completed_at)}</dd>
                {run.approved_at && (
                  <>
                    <dt>Approved</dt>
                    <dd>
                      {formatTime(run.approved_at)}{" "}
                      {run.approved_by ? `by ${run.approved_by}` : ""}
                    </dd>
                  </>
                )}
                {run.human_modified_at && (
                  <>
                    <dt>Modified</dt>
                    <dd>
                      {formatTime(run.human_modified_at)}{" "}
                      {run.human_modified_by ? `by ${run.human_modified_by}` : ""}
                    </dd>
                  </>
                )}
              </dl>
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {title}
    </h4>
  );
}

function ErrorRow({ err }: { err: unknown }) {
  const msg = err instanceof ApiError ? `${err.status} · ${err.message}` : (err as Error).message;
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{msg}</span>
    </div>
  );
}
