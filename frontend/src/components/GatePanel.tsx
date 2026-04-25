import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { gatesApi } from "@/lib/api";
import { AGENT_LABEL, type HumanGate, type InvestigationState } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { Textarea } from "@/components/ui/textarea";
import { GateStatusBadge } from "@/components/StatusBadge";
import { formatRelative } from "@/lib/format";

export function GatePanel({ state }: { state: InvestigationState }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Human Gates</CardTitle>
      </CardHeader>
      <CardContent>
        {state.gates.length === 0 ? (
          <Empty title="No gates yet" description="Gates appear when an agent declares one." />
        ) : (
          <ul className="space-y-3">
            {state.gates.map((g) => (
              <GateRow key={g.id} gate={g} caseId={state.case.id} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function GateRow({ gate, caseId }: { gate: HumanGate; caseId: string }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["case", caseId] });
  const approve = useMutation({
    mutationFn: () => gatesApi.resolve(gate.id, "APPROVED", notes || undefined),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: () => gatesApi.resolve(gate.id, "REJECTED", notes || undefined),
    onSuccess: refresh,
  });
  const open = gate.status === "OPEN_REQUIRED";

  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium">{gate.gate_name}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            Blocks: {AGENT_LABEL[gate.blocks_agent]} · opened {formatRelative(gate.opened_at)}
          </div>
        </div>
        <GateStatusBadge status={gate.status} />
      </div>
      {gate.notes && !open && (
        <p className="mt-2 text-xs italic text-muted-foreground">"{gate.notes}"</p>
      )}
      {open && (
        <div className="mt-2 space-y-2">
          <Textarea
            rows={2}
            placeholder="Optional notes…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="destructive" disabled={reject.isPending} onClick={() => reject.mutate()}>
              Reject
            </Button>
            <Button size="sm" variant="success" disabled={approve.isPending} onClick={() => approve.mutate()}>
              Approve gate
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
