import { useQuery } from "@tanstack/react-query";
import { auditApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Empty } from "@/components/ui/empty";
import { Button } from "@/components/ui/button";
import { formatTime, pretty } from "@/lib/format";
import { ShieldCheck, ShieldAlert } from "lucide-react";

export function AuditTrail({ caseId }: { caseId: string }) {
  const events = useQuery({
    queryKey: ["audit", caseId],
    queryFn: () => auditApi.list(caseId, 200),
  });
  const verify = useQuery({
    queryKey: ["audit-verify", caseId],
    queryFn: () => auditApi.verify(caseId),
  });

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Audit trail</CardTitle>
        <div className="flex items-center gap-2 text-xs">
          {verify.data?.ok ? (
            <span className="inline-flex items-center gap-1 text-success">
              <ShieldCheck className="h-3.5 w-3.5" /> Hash chain verified
            </span>
          ) : verify.data ? (
            <span className="inline-flex items-center gap-1 text-destructive">
              <ShieldAlert className="h-3.5 w-3.5" /> Tampered at id {verify.data.first_bad_id}
            </span>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => events.refetch()}>
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {!events.data || events.data.length === 0 ? (
          <Empty title="No audit events yet" />
        ) : (
          <ol className="space-y-2">
            {events.data.map((e) => (
              <li
                key={e.id}
                className="rounded-md border border-border bg-muted/20 p-2 text-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-muted-foreground">#{e.id}</span>
                    <Badge variant="outline" className="font-mono normal-case">
                      {e.actor_type.toLowerCase()}
                    </Badge>
                    <span className="font-medium">{e.event_type}</span>
                  </div>
                  <span className="text-muted-foreground">{formatTime(e.created_at)}</span>
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">
                  by {e.actor_id}
                </div>
                {Object.keys(e.event_payload).length > 0 && (
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-background/60 p-2 font-mono text-[11px]">
                    {pretty(e.event_payload)}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
