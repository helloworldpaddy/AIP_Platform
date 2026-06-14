import { useMemo } from "react";
import type { A2uiSurfaceState } from "@/lib/a2ui-render";
import {
  actionFromComponent,
  childIds,
  textValue,
  type ActionPayload,
} from "@/lib/a2ui-render";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Props = {
  surface: A2uiSurfaceState;
  onAction?: (action: ActionPayload) => void;
  className?: string;
};

function RenderNode({
  id,
  surface,
  onAction,
}: {
  id: string;
  surface: A2uiSurfaceState;
  onAction?: (action: ActionPayload) => void;
}) {
  const comp = surface.components.get(id);
  if (!comp) return null;

  switch (comp.component) {
    case "Text":
      return (
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{textValue(comp.text)}</p>
      );
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
        <div className="flex flex-col gap-2">
          {childIds(comp.children).map((cid) => (
            <RenderNode key={cid} id={cid} surface={surface} onAction={onAction} />
          ))}
        </div>
      );
    case "Row":
      return (
        <div className="flex flex-wrap items-center gap-2">
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
