import type { Citation, Evidence } from "@/lib/types";
import { Empty } from "@/components/ui/empty";
import { Badge } from "@/components/ui/badge";

interface Props {
  citations: Citation[];
  evidence: Evidence[];
}

export function CitationsList({ citations, evidence }: Props) {
  if (!citations || citations.length === 0) {
    return <Empty title="No citations" description="Agent output had no footnotes." />;
  }
  const lookup = new Map(evidence.map((e) => [e.id, e]));
  const sorted = [...citations].sort((a, b) => a.footnote - b.footnote);

  return (
    <ol className="space-y-3 text-sm">
      {sorted.map((c) => {
        const ev = lookup.get(c.evidence_id);
        return (
          <li key={`${c.footnote}-${c.evidence_id}`} className="flex gap-3">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">
              {c.footnote}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{ev?.title ?? "(evidence not loaded)"}</span>
                {ev && (
                  <Badge variant="outline" className="font-mono normal-case">
                    {ev.evidence_type}
                  </Badge>
                )}
                {ev?.contains_pii && (
                  <Badge variant="warning">PII</Badge>
                )}
              </div>
              {(c.excerpt || ev?.content) && (
                <p className="mt-1 text-xs text-muted-foreground line-clamp-3">
                  {c.excerpt || ev?.content}
                </p>
              )}
              {ev?.source_uri && (
                <a
                  href={ev.source_uri}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-xs text-primary hover:underline"
                >
                  {ev.source_system} · {ev.source_uri}
                </a>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
