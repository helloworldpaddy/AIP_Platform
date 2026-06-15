/**
 * Minimal A2UI v0.9 surface state + helpers (Sprint 8).
 * Full catalog rendering is intentionally narrow — unknown components fall back to JSON.
 */

import type { A2uiMessage } from "@/lib/a2a";

export type A2uiComponent = {
  id: string;
  component: string;
  [key: string]: unknown;
};

export type A2uiSurfaceState = {
  surfaceId: string;
  catalogId?: string;
  components: Map<string, A2uiComponent>;
  rootId?: string;
};

export function applyA2uiMessages(
  surfaces: Map<string, A2uiSurfaceState>,
  messages: A2uiMessage[],
): Map<string, A2uiSurfaceState> {
  const next = new Map(surfaces);
  for (const msg of messages) {
    if (msg.createSurface && typeof msg.createSurface === "object") {
      const cs = msg.createSurface as Record<string, unknown>;
      const surfaceId = String(cs.surfaceId ?? "default");
      next.set(surfaceId, {
        surfaceId,
        catalogId: cs.catalogId as string | undefined,
        components: new Map(next.get(surfaceId)?.components ?? []),
        rootId: next.get(surfaceId)?.rootId,
      });
    }
    if (msg.updateComponents && typeof msg.updateComponents === "object") {
      const uc = msg.updateComponents as Record<string, unknown>;
      const surfaceId = String(uc.surfaceId ?? "default");
      const surface = next.get(surfaceId) ?? {
        surfaceId,
        components: new Map<string, A2uiComponent>(),
      };
      const components = new Map(surface.components);
      const list = uc.components;
      if (Array.isArray(list)) {
        for (const raw of list) {
          if (!raw || typeof raw !== "object") continue;
          const comp = raw as A2uiComponent;
          if (comp.id) components.set(comp.id, comp);
        }
      }
      let rootId = surface.rootId;
      if (!rootId && Array.isArray(list) && list.length === 1) {
        rootId = (list[0] as A2uiComponent).id;
      }
      if (!rootId) {
        const card = [...components.values()].find((c) => c.component === "Card");
        if (card) rootId = card.id;
      }
      next.set(surfaceId, { ...surface, components, rootId });
    }
    if (msg.deleteSurface && typeof msg.deleteSurface === "object") {
      const ds = msg.deleteSurface as Record<string, unknown>;
      next.delete(String(ds.surfaceId ?? "default"));
    }
  }
  return next;
}

export function textValue(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && "literal" in raw) {
    return String((raw as { literal: unknown }).literal);
  }
  return "";
}

export function childIds(raw: unknown): string[] {
  if (typeof raw === "string") return [raw];
  if (Array.isArray(raw)) return raw.map(String);
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.explicitList)) return obj.explicitList.map(String);
  }
  return [];
}

/** List/Tabs children: explicit ids or template binding (path-only). */
export function listChildren(raw: unknown): {
  ids: string[];
  template?: { componentId: string; path: string };
} {
  if (Array.isArray(raw)) return { ids: raw.map(String) };
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.explicitList)) {
      return { ids: obj.explicitList.map(String) };
    }
    const componentId = obj.componentId ?? obj.component_id;
    const path = obj.path ?? obj.dataBinding;
    if (typeof componentId === "string" && typeof path === "string") {
      return { ids: [], template: { componentId, path } };
    }
  }
  return { ids: childIds(raw) };
}

export type TabItem = { title: string; child: string };

export function tabItems(raw: unknown): TabItem[] {
  if (!Array.isArray(raw)) return [];
  const items: TabItem[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    const child = row.child;
    if (typeof child !== "string") continue;
    items.push({
      title: textValue(row.title) || "Tab",
      child,
    });
  }
  return items;
}

export function flexJustify(raw: unknown): string {
  const map: Record<string, string> = {
    start: "justify-start",
    center: "justify-center",
    end: "justify-end",
    spaceBetween: "justify-between",
    spaceAround: "justify-around",
    spaceEvenly: "justify-evenly",
    stretch: "justify-stretch",
  };
  if (typeof raw !== "string") return "justify-start";
  return map[raw] ?? "justify-start";
}

export function flexAlign(raw: unknown): string {
  const map: Record<string, string> = {
    start: "items-start",
    center: "items-center",
    end: "items-end",
    stretch: "items-stretch",
    baseline: "items-baseline",
  };
  if (typeof raw !== "string") return "items-start";
  return map[raw] ?? "items-start";
}

export function textVariantClass(raw: unknown): string {
  const map: Record<string, string> = {
    h1: "text-2xl font-semibold tracking-tight",
    h2: "text-xl font-semibold",
    h3: "text-lg font-medium",
    h4: "text-base font-medium",
    h5: "text-sm font-medium",
    caption: "text-xs text-muted-foreground",
    body: "text-sm leading-relaxed",
  };
  if (typeof raw !== "string") return map.body;
  return map[raw] ?? map.body;
}

export type ActionPayload = {
  name: string;
  context?: Record<string, unknown>;
};

export function actionFromComponent(comp: A2uiComponent): ActionPayload | null {
  const action = comp.action;
  if (!action || typeof action !== "object") return null;
  const a = action as Record<string, unknown>;

  // v0.9: { event: { name, context } }
  const event = a.event;
  if (event && typeof event === "object") {
    const ev = event as Record<string, unknown>;
    const eventName = ev.name ?? ev.actionId ?? ev.id;
    if (typeof eventName === "string") {
      return {
        name: eventName,
        context:
          (ev.context as Record<string, unknown>) ??
          (a.context as Record<string, unknown>) ??
          undefined,
      };
    }
  }

  const name = a.name ?? a.actionId ?? a.id;
  if (typeof name !== "string") return null;
  return {
    name,
    context: (a.context as Record<string, unknown>) ?? undefined,
  };
}

export function actionToUserMessage(action: ActionPayload, caseNumber: string): string {
  const ctx = action.context ? ` ${JSON.stringify(action.context)}` : "";
  return `Case ${caseNumber}: perform action "${action.name}"${ctx}`;
}
