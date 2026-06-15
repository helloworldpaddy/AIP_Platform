import { useState } from "react";
import { LayoutPanelLeft, MessageSquareText } from "lucide-react";
import {
  isAssistantChatAvailable,
  setCaseWorkflowMode,
  type CaseWorkflowMode,
} from "@/lib/case-workflow-mode";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Props = {
  caseNumber: string;
  caseId: string;
  onSelect: (mode: CaseWorkflowMode) => void;
};

export function CaseWorkflowModePicker({ caseNumber, caseId, onSelect }: Props) {
  const assistantAvailable = isAssistantChatAvailable();
  const [selected, setSelected] = useState<CaseWorkflowMode>(
    assistantAvailable ? "assistant" : "standard",
  );
  const [remember, setRemember] = useState(true);

  const start = () => {
    setCaseWorkflowMode(caseId, selected, { rememberAsDefault: remember });
    onSelect(selected);
  };

  return (
    <Card className="border-primary/20">
      <CardHeader>
        <CardTitle>How do you want to work this case?</CardTitle>
        <CardDescription>
          Choose a workflow for <span className="font-mono">{caseNumber}</span>. You can switch
          later from the case header.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <ModeOption
            active={selected === "assistant"}
            disabled={!assistantAvailable}
            icon={MessageSquareText}
            title="Assistant · Chat & A2UI"
            description="Run stages via chat, review interactive summaries, approve from cards. Best for guided investigation."
            bullets={[
              "Agent Assistant + Interactive summary",
              "Approve / verify via structured actions",
              "Step progress + parties & gates alongside",
            ]}
            onClick={() => assistantAvailable && setSelected("assistant")}
          />
          <ModeOption
            active={selected === "standard"}
            icon={LayoutPanelLeft}
            title="Standard · Run panel"
            description="Classic per-stage Run / Approve / Reject panel with full output JSON and reasoning. Best for audit-focused review."
            bullets={[
              "Agent run panel per workflow stage",
              "Full reasoning, overrides, citations",
              "Same gates, parties, and narrative below",
            ]}
            onClick={() => setSelected("standard")}
          />
        </div>

        {!assistantAvailable && (
          <p className="text-xs text-muted-foreground">
            Assistant mode requires the A2A host (<code className="font-mono">--profile a2a</code>
            ). Standard mode is selected.
          </p>
        )}

        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            className="rounded border-border"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          Use this as my default for new cases
        </label>

        <Button type="button" onClick={start} className="w-full sm:w-auto">
          Continue with {selected === "assistant" ? "Assistant" : "Standard"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ModeOption({
  active,
  disabled,
  icon: Icon,
  title,
  description,
  bullets,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  icon: typeof MessageSquareText;
  title: string;
  description: string;
  bullets: string[];
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex flex-col rounded-lg border p-4 text-left transition-colors",
        active
          ? "border-primary bg-primary/5 ring-1 ring-primary/40"
          : "border-border bg-card hover:border-primary/30",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <span className="font-medium text-sm">{title}</span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground leading-relaxed">{description}</p>
      <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
        {bullets.map((b) => (
          <li key={b}>· {b}</li>
        ))}
      </ul>
    </button>
  );
}
