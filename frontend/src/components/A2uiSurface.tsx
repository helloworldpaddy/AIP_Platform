import { useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronRight,
  Circle,
  Info,
  Shield,
  ShieldAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import type { A2uiSurfaceState } from "@/lib/a2ui-render";
import {
  actionFromComponent,
  childIds,
  flexAlign,
  flexJustify,
  listChildren,
  tabItems,
  textValue,
  textVariantClass,
  type ActionPayload,
} from "@/lib/a2ui-render";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type Props = {
  surface: A2uiSurfaceState;
  onAction?: (action: ActionPayload) => void;
  className?: string;
};

const ICONS: Record<string, LucideIcon> = {
  check: Check,
  x: X,
  close: X,
  info: Info,
  alert: AlertCircle,
  warning: AlertCircle,
  shield: Shield,
  shieldalert: ShieldAlert,
  chevronright: ChevronRight,
  circle: Circle,
};

function iconForName(name: string): LucideIcon {
  const key = name.toLowerCase().replace(/[^a-z0-9]/g, "");
  return ICONS[key] ?? Circle;
}

type RenderProps = {
  id: string;
  surface: A2uiSurfaceState;
  onAction?: (action: ActionPayload) => void;
};

function A2uiTabs({
  items,
  surface,
  onAction,
}: {
  items: ReturnType<typeof tabItems>;
  surface: A2uiSurfaceState;
  onAction?: (action: ActionPayload) => void;
}) {
  const [active, setActive] = useState(0);
  const safe = active < items.length ? active : 0;
  const current = items[safe];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1 border-b border-border pb-1">
        {items.map((tab, idx) => (
          <button
            key={`${tab.child}-${idx}`}
            type="button"
            onClick={() => setActive(idx)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              idx === safe
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {tab.title}
          </button>
        ))}
      </div>
      {current && (
        <RenderNode id={current.child} surface={surface} onAction={onAction} />
      )}
    </div>
  );
}

function A2uiModal({
  entryId,
  contentId,
  surface,
  onAction,
}: {
  entryId: string;
  contentId: string;
  surface: A2uiSurfaceState;
  onAction?: (action: ActionPayload) => void;
}) {
  const [open, setOpen] = useState(false);
  const entry = surface.components.get(entryId);

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        className="inline-flex"
        onClick={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        <RenderNode id={entryId} surface={surface} onAction={onAction} />
      </div>
      <Dialog open={open} onClose={() => setOpen(false)} title={textValue(entry?.label)}>
        <RenderNode id={contentId} surface={surface} onAction={onAction} />
      </Dialog>
    </>
  );
}

function RenderNode({ id, surface, onAction }: RenderProps) {
  const comp = surface.components.get(id);
  if (!comp) return null;

  switch (comp.component) {
    case "Text":
      return (
        <p className={cn(textVariantClass(comp.variant), "whitespace-pre-wrap")}>
          {textValue(comp.text)}
        </p>
      );

    case "Divider": {
      const horizontal = comp.axis !== "vertical";
      return (
        <hr
          className={cn(
            "border-border",
            horizontal ? "my-2 w-full border-t" : "mx-2 h-full min-h-6 border-l",
          )}
        />
      );
    }

    case "Icon": {
      const Icon = iconForName(textValue(comp.name));
      return <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />;
    }

    case "List": {
      const direction = comp.direction === "horizontal" ? "horizontal" : "vertical";
      const { ids, template } = listChildren(comp.children);
      if (template) {
        return (
          <p className="rounded-md border border-dashed border-border px-2 py-1 text-xs text-muted-foreground">
            Dynamic list bound to <code className="font-mono">{template.path}</code> — bind data
            in a future pass or use explicit child ids.
          </p>
        );
      }
      return (
        <ul
          className={cn(
            "gap-2",
            direction === "horizontal"
              ? "flex flex-wrap items-center"
              : "flex flex-col divide-y divide-border rounded-md border border-border/60",
          )}
        >
          {ids.map((cid) => (
            <li
              key={cid}
              className={cn(direction === "vertical" && "px-3 py-2 first:pt-2 last:pb-2")}
            >
              <RenderNode id={cid} surface={surface} onAction={onAction} />
            </li>
          ))}
        </ul>
      );
    }

    case "Tabs":
      return (
        <A2uiTabs items={tabItems(comp.tabItems)} surface={surface} onAction={onAction} />
      );

    case "Modal": {
      const entryId = typeof comp.entryPointChild === "string" ? comp.entryPointChild : "";
      const contentId = typeof comp.contentChild === "string" ? comp.contentChild : "";
      if (!entryId || !contentId) return null;
      return (
        <A2uiModal
          entryId={entryId}
          contentId={contentId}
          surface={surface}
          onAction={onAction}
        />
      );
    }

    case "Card":
      return (
        <Card className="border-border/80">
          <CardContent className="p-4 pt-4">
            {childIds(comp.child).map((cid) => (
              <RenderNode key={cid} id={cid} surface={surface} onAction={onAction} />
            ))}
          </CardContent>
        </Card>
      );

    case "Column":
      return (
        <div
          className={cn(
            "flex flex-col gap-2",
            flexJustify(comp.justify),
            flexAlign(comp.align),
          )}
        >
          {childIds(comp.children).map((cid) => (
            <RenderNode key={cid} id={cid} surface={surface} onAction={onAction} />
          ))}
        </div>
      );

    case "Row":
      return (
        <div
          className={cn(
            "flex flex-wrap gap-2",
            flexJustify(comp.justify),
            flexAlign(comp.align),
          )}
        >
          {childIds(comp.children).map((cid) => (
            <RenderNode key={cid} id={cid} surface={surface} onAction={onAction} />
          ))}
        </div>
      );

    case "Button": {
      const action = actionFromComponent(comp);
      const variant =
        comp.variant === "primary"
          ? "default"
          : comp.variant === "borderless"
            ? "ghost"
            : "outline";
      return (
        <Button
          type="button"
          size="sm"
          variant={variant}
          disabled={!action}
          onClick={() => action && onAction?.(action)}
        >
          {childIds(comp.child).map((cid) => (
            <RenderNode key={cid} id={cid} surface={surface} onAction={onAction} />
          ))}
        </Button>
      );
    }

    default:
      return (
        <pre className="overflow-x-auto rounded-md bg-muted/40 p-2 text-[10px]">
          {JSON.stringify(comp, null, 2)}
        </pre>
      );
  }
}

export function A2uiSurface({ surface, onAction, className }: Props) {
  const rootId = useMemo(() => {
    if (surface.rootId && surface.components.has(surface.rootId)) return surface.rootId;
    const first = [...surface.components.values()][0];
    return first?.id;
  }, [surface]);

  if (!rootId) {
    return (
      <p className="text-xs text-muted-foreground">Waiting for A2UI components…</p>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <CardHeader className="p-0 pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          Agent UI · {surface.surfaceId}
        </CardTitle>
      </CardHeader>
      <RenderNode id={rootId} surface={surface} onAction={onAction} />
    </div>
  );
}

/** Example TE surface payload for local Storybook / manual testing. */
export const A2UI_TE_SKETCH_EXAMPLE: {
  surfaceId: string;
  components: A2uiSurfaceState["components"];
  rootId: string;
} = {
  surfaceId: "te-parties-sketch",
  rootId: "root",
  components: new Map([
    ["root", { id: "root", component: "Card", child: "body" }],
    ["body", { id: "body", component: "Column", children: ["header", "tabs", "actions"] }],
    [
      "header",
      {
        id: "header",
        component: "Row",
        children: ["risk-icon", "title"],
        align: "center",
      },
    ],
    ["risk-icon", { id: "risk-icon", component: "Icon", name: "warning" }],
    [
      "title",
      {
        id: "title",
        component: "Text",
        text: "Transaction enrichment",
        variant: "h3",
      },
    ],
    [
      "tabs",
      {
        id: "tabs",
        component: "Tabs",
        tabItems: [
          { title: "Parties", child: "party-list" },
          { title: "Graph", child: "graph-summary" },
        ],
      },
    ],
    [
      "party-list",
      {
        id: "party-list",
        component: "List",
        direction: "vertical",
        children: ["party-1", "party-2"],
      },
    ],
    [
      "party-1",
      {
        id: "party-1",
        component: "Row",
        children: ["p1-text", "p1-btn"],
        justify: "spaceBetween",
        align: "center",
      },
    ],
    [
      "p1-text",
      {
        id: "p1-text",
        component: "Text",
        text: "Counterparty A · hop 1 · correspondent",
      },
    ],
    [
      "p1-btn",
      {
        id: "p1-btn",
        component: "Button",
        variant: "primary",
        child: "p1-label",
        action: {
          event: {
            name: "verify_party",
            context: { partyId: "party-id-1" },
          },
        },
      },
    ],
    ["p1-label", { id: "p1-label", component: "Text", text: "Verify" }],
    [
      "party-2",
      {
        id: "party-2",
        component: "Row",
        children: ["p2-text", "p2-badge"],
        align: "center",
      },
    ],
    [
      "p2-text",
      {
        id: "p2-text",
        component: "Text",
        text: "Counterparty B · hop 2 · verified",
        variant: "caption",
      },
    ],
    ["p2-badge", { id: "p2-badge", component: "Icon", name: "check" }],
    ["divider", { id: "divider", component: "Divider", axis: "horizontal" }],
    [
      "graph-summary",
      {
        id: "graph-summary",
        component: "Text",
        text: "3 counterparties · 2 high-risk jurisdictions",
      },
    ],
    [
      "actions",
      {
        id: "actions",
        component: "Row",
        children: ["approve-btn", "detail-modal"],
        justify: "spaceBetween",
      },
    ],
    [
      "approve-btn",
      {
        id: "approve-btn",
        component: "Button",
        variant: "primary",
        child: "approve-label",
        action: {
          event: {
            name: "approve_run",
            context: { runId: "00000000-0000-4000-8000-000000000001" },
          },
        },
      },
    ],
    ["approve-label", { id: "approve-label", component: "Text", text: "Approve run" }],
    [
      "detail-modal",
      {
        id: "detail-modal",
        component: "Modal",
        entryPointChild: "detail-trigger",
        contentChild: "detail-body",
      },
    ],
    [
      "detail-trigger",
      {
        id: "detail-trigger",
        component: "Button",
        variant: "borderless",
        child: "detail-trigger-label",
      },
    ],
    ["detail-trigger-label", { id: "detail-trigger-label", component: "Text", text: "Details" }],
    [
      "detail-body",
      {
        id: "detail-body",
        component: "Column",
        children: ["detail-title", "detail-text"],
      },
    ],
    [
      "detail-title",
      { id: "detail-title", component: "Text", text: "Graph traversal", variant: "h4" },
    ],
    [
      "detail-text",
      {
        id: "detail-text",
        component: "Text",
        text: "MT103 beneficiary chain via intermediary bank in AE.",
      },
    ],
  ]),
};
