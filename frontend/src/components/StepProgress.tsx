import { cn } from "@/lib/utils";
import { AGENT_LABEL, AGENT_ORDER, type AgentName, type InvestigationState } from "@/lib/types";
import { isBlocked } from "@/lib/state";
import { RunStatusBadge } from "@/components/StatusBadge";
import { CheckCircle2, Circle, Lock, Loader2 } from "lucide-react";

interface Props {
  state: InvestigationState;
  selected: AgentName;
  onSelect: (agent: AgentName) => void;
}

export function StepProgress({ state, selected, onSelect }: Props) {
  return (
    <ol className="flex flex-col gap-2">
      {AGENT_ORDER.map((agent, idx) => {
        const progress = state.progress.find((p) => p.agent === agent);
        const blockingGate = progress?.blocking_gate;
        const blocked = blockingGate != null || isBlocked(state, agent);
        const status = progress?.status ?? "PENDING";
        const isActive = selected === agent;
        const done = ["APPROVED", "MODIFIED", "COMPLETED"].includes(status);
        const running = status === "RUNNING";

        return (
          <li key={agent}>
            <button
              type="button"
              onClick={() => onSelect(agent)}
              className={cn(
                "group w-full rounded-md border p-3 text-left transition-colors",
                isActive
                  ? "border-primary/60 bg-primary/5"
                  : "border-border hover:bg-accent",
              )}
            >
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                  {done ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : running ? (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
                  ) : blocked ? (
                    <Lock className="h-4 w-4 text-warning" />
                  ) : (
                    <Circle className="h-3 w-3 text-muted-foreground" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium">
                      <span className="text-muted-foreground">
                        {String(idx + 1).padStart(2, "0")}
                      </span>{" "}
                      {AGENT_LABEL[agent]}
                    </div>
                    <RunStatusBadge status={status} />
                  </div>
                  {blockingGate ? (
                    <div className="mt-1 text-xs text-warning">
                      Blocked by gate: {blockingGate.gate_name}
                    </div>
                  ) : (
                    <div className="mt-1 text-xs text-muted-foreground">
                      {progress?.completed_at
                        ? `Completed ${new Date(progress.completed_at).toLocaleString()}`
                        : progress?.started_at
                          ? `Started ${new Date(progress.started_at).toLocaleString()}`
                          : "Not started"}
                    </div>
                  )}
                </div>
              </div>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
