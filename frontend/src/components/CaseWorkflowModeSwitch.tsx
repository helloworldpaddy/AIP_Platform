import { LayoutPanelLeft, MessageSquareText } from "lucide-react";
import {
  isAssistantChatAvailable,
  setCaseWorkflowMode,
  workflowModeLabel,
  type CaseWorkflowMode,
} from "@/lib/case-workflow-mode";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  caseId: string;
  mode: CaseWorkflowMode;
  onChange: (mode: CaseWorkflowMode) => void;
  className?: string;
};

export function CaseWorkflowModeSwitch({ caseId, mode, onChange, className }: Props) {
  const assistantAvailable = isAssistantChatAvailable();

  const switchTo = (next: CaseWorkflowMode) => {
    if (next === mode) return;
    if (next === "assistant" && !assistantAvailable) return;
    setCaseWorkflowMode(caseId, next);
    onChange(next);
  };

  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground mr-1">
        Workflow
      </span>
      <Button
        type="button"
        size="sm"
        variant={mode === "assistant" ? "default" : "outline"}
        className="h-7 gap-1 px-2 text-xs"
        disabled={!assistantAvailable}
        onClick={() => switchTo("assistant")}
      >
        <MessageSquareText className="h-3.5 w-3.5" />
        Assistant
      </Button>
      <Button
        type="button"
        size="sm"
        variant={mode === "standard" ? "default" : "outline"}
        className="h-7 gap-1 px-2 text-xs"
        onClick={() => switchTo("standard")}
      >
        <LayoutPanelLeft className="h-3.5 w-3.5" />
        Standard
      </Button>
      <span className="hidden lg:inline text-xs text-muted-foreground ml-1">
        {workflowModeLabel(mode)}
      </span>
    </div>
  );
}
