/**
 * Assistant-mode A2UI layout templates — same run data, different presentation.
 */

import type { A2uiMessage } from "@/lib/a2a";
import type { A2uiLayoutId } from "@/lib/a2ui-layout-preference";
import {
  extractRunSurfaceContent,
  isLowQualityStoredA2ui,
  partialAssessmentNote,
  truncateForDisplay,
} from "@/lib/a2ui-run-content";
import type { AgentRun } from "@/lib/types";

const CATALOG_ID = "https://a2ui.org/schemas/a2ui-basic-catalog-0.9.json";

type Comp = Record<string, unknown>;

export function buildSurfaceMessagesForRun(run: AgentRun, layout: A2uiLayoutId): A2uiMessage[] {
  const payload = run.output_payload as Record<string, unknown> | null;
  const stored = payload?.a2ui_messages;

  if (
    layout === "agent" &&
    Array.isArray(stored) &&
    stored.length > 0 &&
    !isLowQualityStoredA2ui(stored as Record<string, unknown>[])
  ) {
    return stored.filter((e) => e && typeof e === "object") as A2uiMessage[];
  }

  const content = extractRunSurfaceContent(run);
  const surfaceId = `${run.agent.toLowerCase()}-${run.id.slice(0, 8)}`;

  switch (layout) {
    case "executive":
      return wrapSurface(surfaceId, buildExecutiveLayout(content));
    case "detailed":
      return wrapSurface(surfaceId, buildDetailedLayout(content));
    case "analyst":
      return wrapSurface(
        surfaceId,
        content.agent === "TRANSACTION_ENRICHMENT"
          ? buildTeTabsLayout(content)
          : buildAnalystTabsLayout(content),
      );
    case "agent":
      // Agent layout requested but nothing stored — fall back to stage tabs.
      return wrapSurface(
        surfaceId,
        content.agent === "TRANSACTION_ENRICHMENT"
          ? buildTeTabsLayout(content)
          : buildAnalystTabsLayout(content),
      );
    default:
      return wrapSurface(
        surfaceId,
        content.agent === "TRANSACTION_ENRICHMENT"
          ? buildTeTabsLayout(content)
          : buildAnalystTabsLayout(content),
      );
  }
}

function wrapSurface(surfaceId: string, components: Comp[]): A2uiMessage[] {
  return [
    { version: "v0.9", createSurface: { surfaceId, catalogId: CATALOG_ID } },
    { version: "v0.9", updateComponents: { surfaceId, components } },
  ];
}

function statusCaption(content: ReturnType<typeof extractRunSurfaceContent>): string {
  const short = content.runId.slice(0, 8);
  if (content.status === "AWAITING_REVIEW") return `Awaiting review · run ${short}…`;
  return `${content.status.replace(/_/g, " ").toLowerCase()} · run ${short}…`;
}

function actionComponents(
  content: ReturnType<typeof extractRunSurfaceContent>,
  includeRunTe = false,
): Comp[] {
  if (content.status !== "AWAITING_REVIEW") return [];

  const children = ["approve-btn"];
  if (includeRunTe && content.agentLabel.toUpperCase().includes("INITIAL")) {
    children.push("run-te-btn");
  }

  const comps: Comp[] = [
    { id: "actions", component: "Row", children, justify: "start" },
    {
      id: "approve-btn",
      component: "Button",
      variant: "primary",
      child: "approve-label",
      action: { event: { name: "approve_run", context: { runId: content.runId } } },
    },
    { id: "approve-label", component: "Text", text: "Approve run" },
  ];

  if (includeRunTe) {
    comps.push(
      {
        id: "run-te-btn",
        component: "Button",
        variant: "outline",
        child: "run-te-label",
        action: {
          event: { name: "run_stage", context: { agent: "TRANSACTION_ENRICHMENT" } },
        },
      },
      { id: "run-te-label", component: "Text", text: "Run enrichment" },
    );
  }

  return comps;
}

function buildExecutiveLayout(content: ReturnType<typeof extractRunSurfaceContent>): Comp[] {
  const bodyChildren = ["header", "hypothesis-block", "actions"];
  const components: Comp[] = [
    { id: "root", component: "Card", child: "body" },
    { id: "body", component: "Column", children: bodyChildren },
    {
      id: "header",
      component: "Row",
      children: ["risk-icon", "header-text"],
      align: "center",
    },
    {
      id: "risk-icon",
      component: "Icon",
      name: content.riskBand === "HIGH" || content.riskBand === "CRITICAL" ? "warning" : "info",
    },
    {
      id: "header-text",
      component: "Column",
      children: ["title", "status"],
    },
    { id: "title", component: "Text", text: content.agentLabel, variant: "h3" },
    { id: "status", component: "Text", text: statusCaption(content), variant: "caption" },
    { id: "hypothesis-block", component: "Column", children: ["risk-line", "hypo-body"] },
    {
      id: "risk-line",
      component: "Text",
      text: content.riskBand ? `Risk band: ${content.riskBand}` : "Risk band: —",
      variant: "h4",
    },
    {
      id: "hypo-body",
      component: "Text",
      text: truncateForDisplay(content.hypothesis ?? "No leading hypothesis captured for this run."),
      variant: "body",
    },
    ...actionComponents(content),
  ];

  if (content.parseIncomplete || partialAssessmentNote(content)) {
    bodyChildren.push("parse-note");
    components.push({
      id: "parse-note",
      component: "Text",
      text: partialAssessmentNote(content) ?? "",
      variant: "caption",
    });
  }

  return components;
}

function buildDetailedLayout(content: ReturnType<typeof extractRunSurfaceContent>): Comp[] {
  const listChildIds = content.lines.map((_, i) => `detail-${i}`);
  const bodyChildren = ["title", "status", "detail-list", "actions"];

  const components: Comp[] = [
    { id: "root", component: "Card", child: "body" },
    { id: "body", component: "Column", children: bodyChildren },
    { id: "title", component: "Text", text: content.agentLabel, variant: "h3" },
    { id: "status", component: "Text", text: statusCaption(content), variant: "caption" },
    {
      id: "detail-list",
      component: "List",
      direction: "vertical",
      children: listChildIds,
    },
  ];

  content.lines.forEach((line, i) => {
    components.push({
      id: `detail-${i}`,
      component: "Text",
      text: `${line.label}: ${truncateForDisplay(line.value)}`,
      variant: "body",
    });
  });

  components.push(...actionComponents(content, true));

  if (content.parseIncomplete || partialAssessmentNote(content)) {
    bodyChildren.push("parse-note");
    components.push({
      id: "parse-note",
      component: "Text",
      text: partialAssessmentNote(content) ?? "",
      variant: "caption",
    });
  }

  return components;
}

function buildTeTabsLayout(content: ReturnType<typeof extractRunSurfaceContent>): Comp[] {
  const summaryChildren: string[] = [];
  if (content.summary) summaryChildren.push("network-summary");
  if (content.partyCount !== undefined) summaryChildren.push("party-count");
  if (summaryChildren.length === 0) summaryChildren.push("network-summary");

  const cpIds = content.counterparties.map((_, i) => `cp-${i}`);
  const tabItems: Array<{ title: string; child: string }> = [
    { title: "Summary", child: "summary-col" },
  ];
  if (content.counterparties.length > 0) {
    tabItems.push({ title: "Counterparties", child: "counterparties-list" });
  }
  tabItems.push({ title: "Actions", child: "actions-col" });

  const bodyChildren = ["header", "tabs"];
  const components: Comp[] = [
    { id: "root", component: "Card", child: "body" },
    { id: "body", component: "Column", children: bodyChildren },
    {
      id: "header",
      component: "Row",
      children: ["hdr-icon", "hdr-title"],
      align: "center",
    },
    { id: "hdr-icon", component: "Icon", name: "users" },
    {
      id: "hdr-title",
      component: "Column",
      children: ["title", "status"],
    },
    { id: "title", component: "Text", text: content.agentLabel, variant: "h3" },
    { id: "status", component: "Text", text: statusCaption(content), variant: "caption" },
    { id: "tabs", component: "Tabs", tabItems },
    { id: "summary-col", component: "Column", children: summaryChildren },
    {
      id: "network-summary",
      component: "Text",
      text:
        content.summary ??
        (content.counterparties.length > 0
          ? `${content.counterparties.length} counterparties recorded — see Counterparties tab.`
          : "Network summary not captured — review parties in the case panel."),
      variant: "body",
    },
  ];

  if (content.partyCount !== undefined) {
    components.push({
      id: "party-count",
      component: "Text",
      text: `Parties discovered: ${content.partyCount}`,
      variant: "h4",
    });
  }

  if (content.counterparties.length > 0) {
    components.push({
      id: "counterparties-list",
      component: "List",
      direction: "vertical",
      children: cpIds,
    });
    content.counterparties.forEach((cp, i) => {
      const hopRel =
        cp.hop !== undefined
          ? ` · hop ${cp.hop}${cp.relationship ? ` · ${cp.relationship}` : ""}`
          : "";
      components.push({
        id: `cp-${i}`,
        component: "Text",
        text: `${i + 1}. ${cp.name}${hopRel}`,
      });
    });
  }

  const actionComps = actionComponents(content, false);
  components.push({ id: "actions-col", component: "Column", children: ["actions-hint", "actions"] });
  components.push({
    id: "actions-hint",
    component: "Text",
    text: "Approve enrichment, then verify each party in the case panel before Due Diligence.",
    variant: "caption",
  });
  components.push(...actionComps);

  if (content.parseIncomplete || partialAssessmentNote(content)) {
    summaryChildren.push("parse-note");
    components.push({
      id: "parse-note",
      component: "Text",
      text: partialAssessmentNote(content) ?? "",
      variant: "caption",
    });
  }

  return components;
}

function buildAnalystTabsLayout(content: ReturnType<typeof extractRunSurfaceContent>): Comp[] {
  const summaryChildren = ["risk-line"];
  if (content.hypothesis) summaryChildren.push("hypo-label", "hypo-body");
  for (let i = 0; i < content.extras.length; i += 1) {
    summaryChildren.push(`extra-${i}`);
  }

  const questionIds = content.questions.map((_, i) => `q-${i}`);
  const redFlagIds = content.redFlags.map((_, i) => `rf-${i}`);
  const tabItems: Array<{ title: string; child: string }> = [
    { title: "Summary", child: "summary-col" },
  ];
  if (content.redFlags.length > 0) {
    tabItems.push({ title: "Red flags", child: "redflags-list" });
  }
  if (content.questions.length > 0) {
    tabItems.push({ title: "Open questions", child: "questions-list" });
  }
  tabItems.push({ title: "Actions", child: "actions-col" });

  const bodyChildren = ["header", "tabs"];
  const components: Comp[] = [
    { id: "root", component: "Card", child: "body" },
    { id: "body", component: "Column", children: bodyChildren },
    {
      id: "header",
      component: "Row",
      children: ["hdr-icon", "hdr-title"],
      align: "center",
    },
    { id: "hdr-icon", component: "Icon", name: "shield" },
    {
      id: "hdr-title",
      component: "Column",
      children: ["title", "status"],
    },
    { id: "title", component: "Text", text: content.agentLabel, variant: "h3" },
    { id: "status", component: "Text", text: statusCaption(content), variant: "caption" },
    { id: "tabs", component: "Tabs", tabItems },
    { id: "summary-col", component: "Column", children: summaryChildren },
    {
      id: "risk-line",
      component: "Text",
      text: content.riskBand ? `Risk band: ${content.riskBand}` : "Risk band: not assessed",
      variant: "h4",
    },
  ];

  if (content.hypothesis) {
    components.push(
      { id: "hypo-label", component: "Text", text: "Leading hypothesis", variant: "caption" },
      {
        id: "hypo-body",
        component: "Text",
        text: truncateForDisplay(content.hypothesis),
        variant: "body",
      },
    );
  }

  content.extras.forEach((line, i) => {
    components.push({
      id: `extra-${i}`,
      component: "Text",
      text: `${line.label}: ${truncateForDisplay(line.value)}`,
      variant: "body",
    });
  });

  if (content.redFlags.length > 0) {
    components.push({
      id: "redflags-list",
      component: "List",
      direction: "vertical",
      children: redFlagIds,
    });
    content.redFlags.forEach((flag, i) => {
      components.push({
        id: `rf-${i}`,
        component: "Text",
        text: `${i + 1}. ${truncateForDisplay(flag, 400)}`,
      });
    });
  }

  if (content.questions.length > 0) {
    components.push({
      id: "questions-list",
      component: "List",
      direction: "vertical",
      children: questionIds,
    });
    content.questions.forEach((q, i) => {
      components.push({ id: `q-${i}`, component: "Text", text: `${i + 1}. ${q}` });
    });
  }

  const actionComps = actionComponents(content, true);
  components.push({ id: "actions-col", component: "Column", children: ["actions-hint", "actions"] });
  components.push({
    id: "actions-hint",
    component: "Text",
    text: "Human-in-the-loop actions for this run.",
    variant: "caption",
  });
  components.push(...actionComps);

  if (content.parseIncomplete || partialAssessmentNote(content)) {
    summaryChildren.push("parse-note");
    components.push({
      id: "parse-note",
      component: "Text",
      text: partialAssessmentNote(content) ?? "",
      variant: "caption",
    });
  }

  return components;
}
