import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { casesApi, graphApi } from "@/lib/api";
import { isBlocked, latestRun } from "@/lib/state";
import type { AgentName } from "@/lib/types";
import { AGENT_ORDER } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CaseStatusBadge, PriorityBadge } from "@/components/StatusBadge";
import { StepProgress } from "@/components/StepProgress";
import { AgentRunPanel } from "@/components/AgentRunPanel";
import { GatePanel } from "@/components/GatePanel";
import { PartiesPanel } from "@/components/PartiesPanel";
import { NarrativeEditor } from "@/components/NarrativeEditor";
import { AuditTrail } from "@/components/AuditTrail";
import { ChevronLeft, Network, RefreshCw } from "lucide-react";

export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const qc = useQueryClient();
  const stateQuery = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId!),
    enabled: !!caseId,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return false;
      const anyRunning = data.agent_runs.some((r) => r.status === "RUNNING");
      return anyRunning ? 3_000 : false;
    },
  });

  const loadTransactionsToGraph = useMutation({
    mutationFn: () => graphApi.syncTransactionsToNeo4j(caseId!),
    onMutate: () => {
      setLedgerToGraphMessage(null);
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      qc.invalidateQueries({ queryKey: ["case-graph", caseId] });
      setLedgerToGraphMessage(
        data.synced === 0
          ? "No ledger rows to push (add transactions first)."
          : `Loaded ${data.synced} transaction${data.synced === 1 ? "" : "s"} into the graph (Neo4j). Open Graph and enable “include Neo4j hop” to explore.`,
      );
    },
  });

  const [selected, setSelected] = useState<AgentName>("INITIAL_ASSESSMENT");
  const [ledgerToGraphMessage, setLedgerToGraphMessage] = useState<string | null>(null);

  // Auto-focus the most recent active agent on first load.
  useEffect(() => {
    const state = stateQuery.data;
    if (!state) return;
    const candidate =
      [...AGENT_ORDER].reverse().find((a) => latestRun(state, a) !== null) ??
      "INITIAL_ASSESSMENT";
    setSelected((prev) => (prev === "INITIAL_ASSESSMENT" ? candidate : prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateQuery.data?.case.id]);

  const subtitle = useMemo(() => {
    const s = stateQuery.data;
    if (!s) return "";
    const lob = (s.case.line_of_business ?? "RETAIL_BANKING").replace(/_/g, " ").toLowerCase();
    return `${s.case.alert_type} · LOB: ${lob} · subject ${s.case.subject_party_name} (${s.case.subject_party_id})`;
  }, [stateQuery.data]);

  if (!caseId) return null;
  if (stateQuery.isLoading) {
    return <div className="text-sm text-muted-foreground">Loading case…</div>;
  }
  if (stateQuery.error || !stateQuery.data) {
    return (
      <div className="space-y-2">
        <Link to="/" className="inline-flex items-center text-sm text-primary hover:underline">
          <ChevronLeft className="h-4 w-4" /> Back to cases
        </Link>
        <div className="text-sm text-destructive">
          {(stateQuery.error as Error)?.message ?? "Case not found"}
        </div>
      </div>
    );
  }

  const state = stateQuery.data;
  const blockedAgents = AGENT_ORDER.filter((a) => isBlocked(state, a));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/" className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground">
            <ChevronLeft className="h-3.5 w-3.5" /> All cases
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
            <span className="font-mono">{state.case.case_number}</span>
            <CaseStatusBadge status={state.case.status} />
            <PriorityBadge priority={state.case.priority} />
            {state.case.locked && (
              <span className="text-xs text-warning">· locked</span>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
          {blockedAgents.length > 0 && (
            <p className="mt-1 text-xs text-warning">
              {blockedAgents.length} agent{blockedAgents.length > 1 ? "s" : ""} blocked by open gate(s)
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            stage:{" "}
            <span className="font-medium text-foreground">
              {state.case.current_stage.replace(/_/g, " ").toLowerCase()}
            </span>
          </span>
          <span>· assigned: {state.case.assigned_analyst_id ?? "—"}</span>
          <Link to={`/cases/${state.case.id}/graph`}>
            <Button size="sm" variant="ghost">
              <Network className="h-3.5 w-3.5" /> Graph
            </Button>
          </Link>
          <Button size="sm" variant="ghost" onClick={() => stateQuery.refetch()}>
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <aside className="col-span-12 lg:col-span-3">
          <Card>
            <CardHeader>
              <CardTitle>Step progress</CardTitle>
            </CardHeader>
            <CardContent>
              <StepProgress state={state} selected={selected} onSelect={setSelected} />
            </CardContent>
          </Card>
        </aside>

        <section className="col-span-12 lg:col-span-6">
          <AgentRunPanel state={state} agent={selected} />
        </section>

        <aside className="col-span-12 space-y-4 lg:col-span-3">
          <GatePanel state={state} />
          <PartiesPanel state={state} />
          {(state.case_transactions ?? []).length > 0 && (
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0 pb-2">
                <CardTitle className="text-base">Case transactions</CardTitle>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={loadTransactionsToGraph.isPending}
                  title="Copy ledger rows from Postgres into Neo4j for graph hops"
                  onClick={() => loadTransactionsToGraph.mutate()}
                >
                  {loadTransactionsToGraph.isPending ? "Loading…" : "Load transactions to graph"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                {(ledgerToGraphMessage || loadTransactionsToGraph.isError) && (
                  <div className="space-y-1 rounded-md border border-border bg-muted/30 p-2">
                    {ledgerToGraphMessage && (
                      <p className="text-muted-foreground">{ledgerToGraphMessage}</p>
                    )}
                    {loadTransactionsToGraph.isError && (
                      <p className="text-destructive">
                        {(loadTransactionsToGraph.error as Error)?.message ??
                          "Could not load transactions to graph (is Neo4j configured?)"}
                      </p>
                    )}
                  </div>
                )}
                {(state.case_transactions ?? []).map((t) => (
                  <div
                    key={t.id}
                    className="border-b border-border pb-2 last:border-0 last:pb-0"
                  >
                    <div className="font-mono text-[11px] text-muted-foreground">
                      {t.external_transaction_id}
                    </div>
                    <div className="mt-0.5 font-medium">
                      {String(t.amount)} {t.currency} · {t.direction} ·{" "}
                      {t.payment_channel.replace(/_/g, " ")}
                    </div>
                    <div className="text-muted-foreground">
                      {t.product_category.replace(/_/g, " ")}
                      {t.counterparty_name ? ` · ${t.counterparty_name}` : ""}
                      {t.counterparty_country ? ` (${t.counterparty_country})` : ""}
                    </div>
                    {t.narrative && (
                      <div className="mt-1 text-muted-foreground">{t.narrative}</div>
                    )}
                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                      {new Date(t.booked_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </aside>
      </div>

      <NarrativeEditor state={state} />

      <AuditTrail caseId={state.case.id} />
    </div>
  );
}
