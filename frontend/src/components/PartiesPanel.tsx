import { useMutation, useQueryClient } from "@tanstack/react-query";
import { partiesApi } from "@/lib/api";
import type { CaseParty, InvestigationState } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, ShieldCheck } from "lucide-react";

export function PartiesPanel({ state }: { state: InvestigationState }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Case parties</CardTitle>
      </CardHeader>
      <CardContent>
        {state.parties.length === 0 ? (
          <Empty
            title="No parties recorded"
            description="Transaction Enrichment will populate counterparties here."
          />
        ) : (
          <ul className="space-y-2">
            {state.parties.map((p) => (
              <PartyRow key={p.id} party={p} caseId={state.case.id} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PartyRow({ party, caseId }: { party: CaseParty; caseId: string }) {
  const qc = useQueryClient();
  const verify = useMutation({
    mutationFn: () => partiesApi.verify(party.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }),
  });

  return (
    <li className="flex items-start justify-between gap-2 rounded-md border border-border p-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {party.party_name}
          <Badge variant="outline" className="font-mono normal-case">
            {party.party_type}
          </Badge>
          <Badge variant="secondary">hop {party.hop_distance}</Badge>
          {party.relationship && (
            <span className="text-xs font-normal text-muted-foreground">
              · {party.relationship}
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {party.party_external_id}
        </div>
      </div>
      {party.verified ? (
        <Badge variant="success" className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" /> Verified
        </Badge>
      ) : (
        <Button size="sm" variant="success" disabled={verify.isPending} onClick={() => verify.mutate()}>
          <ShieldCheck className="h-3.5 w-3.5" /> Verify
        </Button>
      )}
    </li>
  );
}
