import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, Send, Sparkles } from "lucide-react";
import { casesApi } from "@/lib/api";
import {
  A2aClientError,
  fetchAgentCard,
  sendMessageStream,
  type StreamEvent,
} from "@/lib/a2a";
import { dispatchA2uiAction } from "@/lib/a2ui-actions";
import {
  getA2uiLayoutPreference,
  subscribeA2uiLayoutPreference,
  type A2uiLayoutId,
} from "@/lib/a2ui-layout-preference";
import { runsWithSurfaces, surfacesFromRuns } from "@/lib/a2ui-from-run";
import {
  applyA2uiMessages,
  type A2uiSurfaceState,
  type ActionPayload,
} from "@/lib/a2ui-render";
import { A2uiSurface } from "@/components/A2uiSurface";
import { A2uiLayoutSelector } from "@/components/A2uiLayoutSelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type ChatMessage = {
  id: string;
  role: "user" | "agent" | "system";
  text: string;
};

type Props = {
  caseNumber: string;
  caseId: string;
};

const ENABLED =
  (import.meta.env.VITE_AML_AGENT_CHAT_ENABLED as string | undefined)?.toLowerCase() !==
  "false";

export function AgentChatPanel({ caseNumber, caseId }: Props) {
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamSurfaces, setStreamSurfaces] = useState<Map<string, A2uiSurfaceState>>(
    new Map(),
  );
  const [contextId, setContextId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [seeded, setSeeded] = useState(false);
  const [a2uiLayout, setA2uiLayout] = useState<A2uiLayoutId>(() => getA2uiLayoutPreference());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return subscribeA2uiLayoutPreference(() => setA2uiLayout(getA2uiLayoutPreference()));
  }, []);

  const cardQuery = useQuery({
    queryKey: ["a2a-agent-card"],
    queryFn: fetchAgentCard,
    retry: false,
    staleTime: 60_000,
    enabled: ENABLED,
  });

  const caseQuery = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId),
    enabled: ENABLED && !!caseId,
  });

  const runSurfaces = useMemo(() => {
    const runs = runsWithSurfaces(caseQuery.data?.agent_runs ?? []);
    return surfacesFromRuns(runs, a2uiLayout);
  }, [caseQuery.data?.agent_runs, a2uiLayout]);

  const displaySurfaces = useMemo(() => {
    const merged = new Map(runSurfaces);
    for (const [id, surface] of streamSurfaces) {
      merged.set(id, surface);
    }
    return merged;
  }, [runSurfaces, streamSurfaces]);

  const appendMessage = useCallback((role: ChatMessage["role"], text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role, text: trimmed }]);
  }, []);

  const runTurn = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;
      appendMessage("user", text);
      setStreaming(true);
      setStatus("connecting…");

      let agentBuffer = "";
      const flushAgent = () => {
        if (agentBuffer.trim()) {
          appendMessage("agent", agentBuffer);
          agentBuffer = "";
        }
      };

      try {
        for await (const event of sendMessageStream({
          text,
          card: cardQuery.data ?? null,
          contextId,
        })) {
          consumeEvent(event, {
            onText: (t) => {
              agentBuffer += t;
            },
            onA2ui: (msgs) => {
              flushAgent();
              setStreamSurfaces((prev) => applyA2uiMessages(prev, msgs));
            },
            onStatus: (state, final) => {
              setStatus(state);
              if (final) flushAgent();
            },
            onSession: (ctx) => {
              if (ctx) setContextId(ctx);
            },
            onError: (msg) => appendMessage("system", msg),
            onDone: () => {
              flushAgent();
              setStatus(null);
            },
          });
        }
        await qc.invalidateQueries({ queryKey: ["case", caseId] });
        await qc.refetchQueries({ queryKey: ["case", caseId] });
      } catch (err) {
        appendMessage(
          "system",
          err instanceof A2aClientError ? err.message : (err as Error).message,
        );
      } finally {
        setStreaming(false);
        setStatus(null);
      }
    },
    [appendMessage, cardQuery.data, caseId, contextId, qc, streaming],
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, displaySurfaces]);

  useEffect(() => {
    if (!ENABLED || seeded || !cardQuery.data) return;
    setSeeded(true);
  }, [cardQuery.data, seeded]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    void runTurn(text);
  };

  const onA2uiAction = (action: ActionPayload) => {
    void dispatchA2uiAction(action, {
      caseId,
      caseNumber,
      invalidateCase: async () => {
        await qc.invalidateQueries({ queryKey: ["case", caseId] });
        await qc.refetchQueries({ queryKey: ["case", caseId] });
      },
      onChatFallback: (message) => void runTurn(message),
      onSuccess: (message) => appendMessage("system", message),
      onError: (message) => appendMessage("system", `Action failed: ${message}`),
    });
  };

  if (!ENABLED) return null;

  const hasSurfaces = displaySurfaces.size > 0;

  return (
    <Card className="col-span-12">
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <CardTitle className="text-base">Agent Assistant</CardTitle>
        </div>
        <span className="text-xs text-muted-foreground">
          A2A · {cardQuery.data?.name ?? "aml-host"}
        </span>
      </CardHeader>
      <CardContent className="space-y-3">
        <A2uiLayoutSelector value={a2uiLayout} onChange={setA2uiLayout} />

        {cardQuery.isError && (
          <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning-foreground">
            {(cardQuery.error as Error).message} — start{" "}
            <code className="font-mono">docker compose --profile a2a</code> to enable the host
            agent on <code className="font-mono">/a2a</code>.
          </p>
        )}

        <div
          ref={scrollRef}
          className="max-h-[min(28rem,60vh)] space-y-3 overflow-y-auto rounded-md border border-border bg-muted/20 p-3"
        >
          {messages.length === 0 && cardQuery.data && !streaming && (
            <p className="text-xs text-muted-foreground">
              Connected to {cardQuery.data.name}. Ask to run a stage (e.g. &quot;run initial
              assessment&quot;) or check case state for {caseNumber}.
            </p>
          )}
          {messages.length === 0 && !cardQuery.isLoading && !cardQuery.data && (
            <p className="text-xs text-muted-foreground">
              Ask to run a stage, check case state, approve a run, or verify parties.
            </p>
          )}
          {messages.map((m) => (
            <div
              key={m.id}
              className={cn(
                "flex gap-2 text-sm",
                m.role === "user" && "justify-end",
                m.role === "system" && "text-destructive",
              )}
            >
              {m.role === "agent" && <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />}
              <div
                className={cn(
                  "max-w-[95%] rounded-md px-2.5 py-1.5 whitespace-pre-wrap",
                  m.role === "user" && "bg-primary text-primary-foreground",
                  m.role === "agent" && "bg-card border border-border",
                  m.role === "system" && "bg-destructive/10 border border-destructive/30 text-xs",
                )}
              >
                {m.text}
              </div>
            </div>
          ))}

          {/* A2UI surfaces inline in the conversation (below latest agent text) */}
          {hasSurfaces && (
            <div className="space-y-3 border-t border-border/60 pt-3">
              <p className="text-xs font-medium text-muted-foreground">Interactive summary</p>
              {[...displaySurfaces.values()].map((surface) => (
                <A2uiSurface
                  key={surface.surfaceId}
                  surface={surface}
                  onAction={onA2uiAction}
                  className="bg-card/50"
                />
              ))}
            </div>
          )}

          {streaming && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {status ?? "Thinking…"}
            </div>
          )}

          {!hasSurfaces && !streaming && caseQuery.data && messages.length > 0 && (
            <p className="text-xs text-muted-foreground border-t border-border/60 pt-2">
              No A2UI panel yet — run a stage to generate an interactive summary with approve
              actions.
            </p>
          )}
        </div>

        <form onSubmit={onSubmit} className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Message about ${caseNumber}…`}
            rows={2}
            disabled={streaming || cardQuery.isError}
            className="min-h-[2.5rem] resize-none text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e);
              }
            }}
          />
          <Button
            type="submit"
            size="icon"
            disabled={streaming || !input.trim() || cardQuery.isError}
            aria-label="Send"
          >
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function consumeEvent(
  event: StreamEvent,
  handlers: {
    onText: (text: string) => void;
    onA2ui: (messages: Record<string, unknown>[]) => void;
    onStatus: (state: string, final?: boolean) => void;
    onSession: (contextId?: string, taskId?: string) => void;
    onError: (message: string) => void;
    onDone: () => void;
  },
) {
  switch (event.type) {
    case "text":
      if (event.role === "agent") handlers.onText(event.text);
      break;
    case "a2ui":
      handlers.onA2ui(event.messages);
      break;
    case "status":
      handlers.onStatus(event.state, event.final);
      break;
    case "session":
      handlers.onSession(event.contextId, event.taskId);
      break;
    case "error":
      handlers.onError(event.message);
      break;
    case "done":
      handlers.onDone();
      break;
    default:
      break;
  }
}
