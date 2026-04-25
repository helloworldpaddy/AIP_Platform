import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { narrativesApi } from "@/lib/api";
import { currentDraftNarrative, submittedNarrative } from "@/lib/state";
import type { InvestigationState } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Empty } from "@/components/ui/empty";
import { Badge } from "@/components/ui/badge";
import { ClassificationBadge } from "@/components/StatusBadge";
import { CitationsList } from "@/components/CitationsList";
import { Send, Save, Lock } from "lucide-react";

export function NarrativeEditor({ state }: { state: InvestigationState }) {
  const qc = useQueryClient();
  const submitted = submittedNarrative(state);
  const draft = currentDraftNarrative(state);
  const active = submitted ?? draft;

  const [rationale, setRationale] = useState("");
  const [body, setBody] = useState("");

  useEffect(() => {
    setRationale(active?.rationale ?? "");
    setBody(active?.markdown_body ?? "");
  }, [active?.id, active?.version, active?.rationale, active?.markdown_body]);

  const save = useMutation({
    mutationFn: () =>
      narrativesApi.update(active!.id, { rationale, markdown_body: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", state.case.id] }),
  });

  const submit = useMutation({
    mutationFn: () => narrativesApi.submit(active!.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", state.case.id] }),
  });

  if (!active) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Narrative</CardTitle>
        </CardHeader>
        <CardContent>
          <Empty
            title="No narrative drafted yet"
            description="The Case Analysis agent produces the SAR / disposition narrative."
          />
        </CardContent>
      </Card>
    );
  }

  const locked = active.locked || active.submitted;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <CardTitle>Narrative · v{active.version}</CardTitle>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <ClassificationBadge value={active.classification} />
            {active.human_modified && <Badge variant="warning">Human-modified</Badge>}
            {active.submitted ? (
              <Badge variant="success" className="flex items-center gap-1">
                <Lock className="h-3 w-3" /> Submitted{active.submitted_by ? ` by ${active.submitted_by}` : ""}
              </Badge>
            ) : (
              <Badge variant="info">Draft</Badge>
            )}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={locked || save.isPending}
            onClick={() => save.mutate()}
          >
            <Save className="h-3.5 w-3.5" /> Save
          </Button>
          <Button
            size="sm"
            variant="success"
            disabled={locked || submit.isPending}
            onClick={() => submit.mutate()}
          >
            <Send className="h-3.5 w-3.5" /> Submit
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Rationale
          </label>
          <Textarea
            className="mt-1"
            rows={3}
            value={rationale}
            disabled={locked}
            onChange={(e) => setRationale(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Narrative body (markdown)
          </label>
          <Textarea
            className="mt-1 min-h-[260px] font-mono text-xs"
            value={body}
            disabled={locked}
            onChange={(e) => setBody(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Citations
          </label>
          <div className="mt-2">
            <CitationsList citations={active.citations} evidence={state.evidence} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
