import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ForceGraph2D from "react-force-graph-2d";
import { ChevronLeft, RefreshCw, Network } from "lucide-react";
import { graphApi } from "@/lib/api";
import type { GraphLink, GraphNode } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Empty } from "@/components/ui/empty";

type RenderNode = GraphNode & { color: string; val: number };
type RenderLink = GraphLink & { color: string };

function linkStroke(link: GraphLink): string {
  const pl = link.metadata?.neo4j_path_length;
  if (typeof pl === "number" && pl >= 2) return "#c084fc"; // hop-2+ (Neo4j path length)
  if (link.metadata?.source === "neo4j" || link.metadata?.neo4j_path_length != null) {
    return "#818cf8"; // Neo4j hop-1 (or merged neo4j metadata)
  }
  return "#475569"; // case_parties / non-Neo4j
}

function linkCaption(link: GraphLink): string {
  const rel = link.relationship || "RELATED";
  const pl = link.metadata?.neo4j_path_length;
  if (typeof pl === "number" && pl > 0) {
    return `${rel} · Neo4j path ${pl} hop${pl === 1 ? "" : "s"}`;
  }
  return rel;
}

const KIND_COLOR: Record<GraphNode["kind"], string> = {
  subject: "#f97316",
  party: "#38bdf8",
  account: "#a78bfa",
  transaction: "#facc15",
};

function nodeColor(node: GraphNode): string {
  const flags = node.risk_indicators ?? {};
  if (flags.is_pep || flags.high_risk_country || flags.is_shell) return "#ef4444";
  return KIND_COLOR[node.kind] ?? "#94a3b8";
}

function nodeSize(node: GraphNode): number {
  if (node.kind === "subject") return 8;
  if ((node.hop_distance ?? 1) <= 1) return 5;
  return 3.5;
}

export function CaseGraphPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const qc = useQueryClient();
  const [includeNeo4j, setIncludeNeo4j] = useState(false);
  const [hop, setHop] = useState(1);

  const graphQuery = useQuery({
    queryKey: ["case-graph", caseId, includeNeo4j, hop],
    queryFn: () => graphApi.get(caseId!, { includeNeo4j, hop }),
    enabled: !!caseId,
  });

  const syncNeo4j = useMutation({
    mutationFn: () => graphApi.syncTransactionsToNeo4j(caseId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case-graph", caseId] });
      qc.invalidateQueries({ queryKey: ["case", caseId] });
    },
  });

  // ForceGraph2D mutates link source/target into node refs. Clone before render
  // so the React Query cache stays a plain JSON snapshot the rest of the app
  // can re-read.
  const data = useMemo(() => {
    const src = graphQuery.data;
    if (!src) return { nodes: [] as RenderNode[], links: [] as RenderLink[] };
    return {
      nodes: src.nodes.map((n) => ({
        ...n,
        color: nodeColor(n),
        val: nodeSize(n),
      })),
      links: src.links.map((l) => ({
        ...l,
        color: linkStroke(l),
      })),
    };
  }, [graphQuery.data]);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: Math.max(480, el.clientHeight) });
    });
    ro.observe(el);
    setSize({ w: el.clientWidth, h: Math.max(480, el.clientHeight) });
    return () => ro.disconnect();
  }, []);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = data.nodes.find((n) => n.id === selectedId) ?? null;

  if (!caseId) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            to={`/cases/${caseId}`}
            className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Back to case
          </Link>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Network className="h-5 w-5 text-primary" /> Investigation graph
          </h1>
          <p className="text-sm text-muted-foreground">
            Force-directed view of the case subject and related parties. With{" "}
            <span className="text-foreground">include Neo4j hop</span>, counterparties
            from synced ledger data are added; each is drawn as one edge from the
            subject (multi-step paths are not drawn as chains).{" "}
            <span className="text-foreground">2 hops</span> only changes the result if
            there are parties reachable in two graph relationships who are not already
            reachable in one.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={includeNeo4j}
              onChange={(e) => setIncludeNeo4j(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            include Neo4j hop
          </label>
          <select
            value={hop}
            onChange={(e) => setHop(Number(e.target.value))}
            disabled={!includeNeo4j}
            className="h-8 rounded-md border border-border bg-background px-2 text-xs"
          >
            <option value={1}>1 hop</option>
            <option value={2}>2 hops</option>
          </select>
          <Button size="sm" variant="ghost" onClick={() => graphQuery.refetch()}>
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={!caseId || syncNeo4j.isPending}
            title="Copies case ledger rows from Postgres into Neo4j so you can expand hops on the graph (idempotent)."
            onClick={() => syncNeo4j.mutate()}
          >
            {syncNeo4j.isPending ? "Loading…" : "Load transactions to graph"}
          </Button>
        </div>
      </div>
      {syncNeo4j.isSuccess && syncNeo4j.data != null && (
        <p className="text-xs text-muted-foreground">
          Loaded {syncNeo4j.data.synced} ledger row
          {syncNeo4j.data.synced === 1 ? "" : "s"} into Neo4j. Turn on{" "}
          <span className="font-medium text-foreground">include Neo4j hop</span>{" "}
          and refresh to traverse counterparties.
        </p>
      )}
      {syncNeo4j.isError && (
        <p className="text-xs text-destructive">
          {(syncNeo4j.error as Error)?.message ?? "Could not load transactions to graph."}
        </p>
      )}

      <div className="grid grid-cols-12 gap-4">
        <section className="col-span-12 lg:col-span-9">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>
                {graphQuery.data ? (
                  <span className="flex items-center gap-2 text-base">
                    {data.nodes.length} nodes · {data.links.length} edges
                    <Badge variant="outline" className="font-mono text-[10px]">
                      source: {graphQuery.data.source}
                    </Badge>
                  </span>
                ) : (
                  <span className="text-base">Loading graph…</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div
                ref={containerRef}
                className="h-[600px] w-full overflow-hidden rounded-md border border-border bg-muted/20"
              >
                {graphQuery.isLoading ? (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    Loading…
                  </div>
                ) : graphQuery.error ? (
                  <div className="flex h-full items-center justify-center text-sm text-destructive">
                    {(graphQuery.error as Error).message}
                  </div>
                ) : data.nodes.length === 0 ? (
                  <Empty
                    title="No graph data"
                    description="Trigger Transaction Enrichment to populate counterparties."
                  />
                ) : (
                  <ForceGraph2D
                    graphData={data}
                    width={size.w}
                    height={size.h}
                    nodeId="id"
                    nodeLabel={(n: RenderNode) =>
                      `${n.label} (${n.kind}${n.hop_distance != null ? `, hop ${n.hop_distance}` : ""})`
                    }
                    linkLabel={(l: RenderLink) => linkCaption(l)}
                    linkDirectionalArrowLength={3}
                    linkDirectionalArrowRelPos={1}
                    linkColor={(l: RenderLink) => l.color}
                    linkWidth={(l: RenderLink) => Math.min(4, 0.5 + Math.log10(l.weight + 1))}
                    cooldownTicks={80}
                    onNodeClick={(n: RenderNode) =>
                      setSelectedId((prev) => (prev === n.id ? null : n.id))
                    }
                    nodeCanvasObjectMode={() => "after"}
                    nodeCanvasObject={(node: RenderNode & { x?: number; y?: number }, ctx, globalScale) => {
                      if (globalScale < 1.2 && node.kind !== "subject") return;
                      const label = node.label;
                      const fontSize = 11 / globalScale;
                      ctx.font = `${fontSize}px system-ui, sans-serif`;
                      ctx.fillStyle = "rgba(226,232,240,0.9)";
                      ctx.textAlign = "center";
                      ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + 10);
                    }}
                  />
                )}
              </div>
            </CardContent>
          </Card>
        </section>

        <aside className="col-span-12 lg:col-span-3">
          <Card>
            <CardHeader>
              <CardTitle>{selected ? "Node detail" : "Legend"}</CardTitle>
            </CardHeader>
            <CardContent>
              {selected ? <NodeDetail node={selected} /> : <Legend />}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <ul className="space-y-2 text-xs">
      <Swatch color={KIND_COLOR.subject} label="Subject (case focus)" />
      <Swatch color={KIND_COLOR.party} label="Related party" />
      <Swatch color="#ef4444" label="Risk-flagged (PEP / shell / high-risk)" />
      <li className="border-t border-border pt-2 text-[11px] font-medium text-muted-foreground">
        Edges
      </li>
      <Swatch color="#475569" label="Case parties (from enrichment)" />
      <Swatch color="#818cf8" label="Neo4j path length 1" />
      <Swatch color="#c084fc" label="Neo4j path length 2" />
      <li className="pt-2 text-muted-foreground">
        Hover an edge for its label. Toggle Neo4j and use Refresh after syncing
        ledger rows to Neo4j.
      </li>
    </ul>
  );
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span
        aria-hidden
        className="inline-block h-3 w-3 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </li>
  );
}

function NodeDetail({ node }: { node: RenderNode }) {
  const flags = Object.entries(node.risk_indicators ?? {}).filter(
    ([, v]) => v === true || (typeof v === "number" && v > 0),
  );
  return (
    <div className="space-y-2 text-xs">
      <div className="text-sm font-semibold">{node.label}</div>
      <div className="font-mono text-muted-foreground">{node.id}</div>
      <div className="flex flex-wrap gap-1">
        <Badge variant="outline">{node.kind}</Badge>
        {node.party_type && <Badge variant="outline">{node.party_type}</Badge>}
        {node.hop_distance != null && (
          <Badge variant="secondary">hop {node.hop_distance}</Badge>
        )}
        {node.verified && <Badge variant="success">verified</Badge>}
      </div>
      {flags.length > 0 && (
        <div>
          <div className="mb-1 text-muted-foreground">Risk indicators</div>
          <ul className="space-y-1">
            {flags.map(([k, v]) => (
              <li key={k} className="flex justify-between">
                <span>{k}</span>
                <span className="font-mono">{String(v)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
