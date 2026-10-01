import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Bot, ChevronRight, Info, Send, ShieldAlert, Sparkles, Terminal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { EmptyState, ErrorNotice, Kbd, Panel, Pill, Spinner } from "@/components/common/ui";
import { RequireConnection } from "@/components/layout/require-connection";
import { ChartView } from "@/components/query/chart-view";
import { ExportMenu } from "@/components/query/export-menu";
import { ResultsTable } from "@/components/query/results-table";
import { RichText } from "@/components/query/rich-text";
import { SqlBlock } from "@/components/query/sql-block";
import { AttemptsTimeline, GuardrailPills, JudgePanel, VerdictBadge } from "@/components/query/trust";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { api, type AskResponse, type Connection } from "@/lib/api";
import { formatInt, formatMs } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace, type ChatTurn } from "@/state/workspace";

export const Route = createFileRoute("/_app/ask")({
  head: () => ({ meta: [{ title: "Ask AI — AskDB" }] }),
  component: () => <RequireConnection>{(connection) => <AskContent key={connection.connection_id} connection={connection} />}</RequireConnection>,
});

const STAGES = ["Understanding your question…", "Writing SQL…", "Running it safely…", "Reviewing the result…"];
const MAX_LEN = 1000;

function useStageLabel(active: boolean): string {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(() => setIndex((i) => Math.min(i + 1, STAGES.length - 1)), 2600);
    return () => window.clearInterval(timer);
  }, [active]);
  return STAGES[index] ?? STAGES[0] ?? "";
}

function Details({ summary, children, defaultOpen = false }: { summary: string; children: React.ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group rounded-md border border-border">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className="border-t border-border p-3">{children}</div>
    </details>
  );
}

function PendingCard() {
  const label = useStageLabel(true);
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground" role="status">
      <Spinner className="text-accent" />
      <span>{label}</span>
    </div>
  );
}

function ResponseCard({ connection, response }: { connection: Connection; response: AskResponse }) {
  const navigate = useNavigate();
  const { ask, setSqlDraft } = useWorkspace();

  const openInEditor = () => {
    if (!response.sql) return;
    setSqlDraft(response.sql);
    void navigate({ to: "/sql" });
  };

  if (response.status === "clarification") {
    return (
      <div className="flex gap-3 rounded-lg border border-border bg-card p-4">
        <Info className="mt-0.5 size-4 shrink-0 text-accent" />
        <div className="space-y-1 text-sm">
          <p className="font-semibold">{response.clarification_type === "ambiguous" ? "I need a bit more detail" : "This isn't in your data"}</p>
          <p className="text-foreground/80">{response.message}</p>
        </div>
      </div>
    );
  }

  if (response.status === "blocked" || response.status === "failed") {
    const blocked = response.status === "blocked";
    return (
      <div className={cn("space-y-3 rounded-lg border p-4", blocked ? "border-warning/30 bg-warning/5" : "border-danger/30 bg-danger/5")}>
        <div className="flex gap-3">
          <ShieldAlert className={cn("mt-0.5 size-4 shrink-0", blocked ? "text-warning" : "text-danger")} />
          <div className="min-w-0 space-y-1 text-sm">
            <p className={cn("font-semibold", blocked ? "text-warning" : "text-danger")}>{blocked ? "Blocked by guardrails" : "Couldn't answer that"}</p>
            <p className="break-words text-foreground/80">{response.message}</p>
          </div>
        </div>
        {response.attempts.length > 0 && (
          <Details summary={`What was tried (${response.attempts.length})`}>
            <AttemptsTimeline attempts={response.attempts} />
          </Details>
        )}
      </div>
    );
  }

  const result = response.result;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <VerdictBadge judge={response.judge} lowConfidence={response.low_confidence} />
        <GuardrailPills guardrails={response.guardrails} />
        {response.retries > 0 && <Pill tone="accent" title="The first attempt failed or was reviewed as wrong; the query was fixed automatically">Auto-fixed ×{response.retries}</Pill>}
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">{formatMs(response.execution_time * 1000)}</span>
      </div>

      {response.low_confidence && (
        <p className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-[13px] text-foreground/80">
          The reviewer isn't fully confident this answers your question. Check the SQL below before relying on it.
        </p>
      )}

      {response.answer && <RichText text={response.answer} />}

      {response.assumptions.length > 0 && (
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold">Assumed:</span> {response.assumptions.join(" · ")}
        </p>
      )}

      {response.chart && result && <ChartView spec={response.chart} rows={result.rows} />}

      {result && (
        <Panel
          title="Results"
          meta={`${formatInt(result.row_count)} row${result.row_count === 1 ? "" : "s"}${result.truncated ? " (row limit reached)" : ""}`}
          actions={
            <ExportMenu
              disabled={result.row_count === 0}
              source={response.sql ? { kind: "query", body: { connection_id: connection.connection_id, sql_query: response.sql }, name: "ask_results" } : null}
            />
          }
        >
          {result.redacted_columns.length > 0 && (
            <p className="border-b border-border bg-warning/5 px-4 py-2 text-xs text-foreground/80">
              Restricted columns are masked: {result.redacted_columns.join(", ")}
            </p>
          )}
          <ResultsTable result={result} className="max-h-80" />
        </Panel>
      )}

      {response.sql && (
        <Details summary="SQL">
          <SqlBlock
            sql={response.sql}
            actions={
              <Button variant="ghost" size="sm" onClick={openInEditor}>
                <Terminal className="size-3.5" />
                Open in editor
              </Button>
            }
          />
        </Details>
      )}
      <Details summary="How this was checked">
        <div className="space-y-4">
          <JudgePanel judge={response.judge} />
          {response.attempts.length > 1 && (
            <div>
              <p className="mb-2 text-xs font-semibold text-muted-foreground">Attempts</p>
              <AttemptsTimeline attempts={response.attempts} />
            </div>
          )}
          <p className="font-mono text-[11px] text-muted-foreground">
            generator: {response.model_used ?? "—"} · total {formatMs(response.timings["total_ms"])}
          </p>
        </div>
      </Details>

      {response.follow_ups && response.follow_ups.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1">
          {response.follow_ups.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => void ask(q)}
              className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-accent/40 hover:bg-accent/5 hover:text-foreground"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Turn({ turn, connection }: { turn: ChatTurn; connection: Connection }) {
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-lg rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">{turn.question}</p>
      </div>
      <div className="flex gap-3">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-accent/10 text-accent">
          <Bot className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          {turn.status === "pending" && <PendingCard />}
          {turn.status === "error" && <ErrorNotice title="Request failed" message={turn.error ?? "Unknown error"} />}
          {turn.status === "done" && turn.response && <ResponseCard connection={connection} response={turn.response} />}
        </div>
      </div>
    </div>
  );
}

function AskContent({ connection }: { connection: Connection }) {
  const id = connection.connection_id;
  const { turns, isAsking, ask, clearChat, askDraft, setAskDraft } = useWorkspace();
  const overview = useQuery({ queryKey: ["overview", id], queryFn: () => api.overview(id) });
  const [text, setText] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Hand-off from other pages ("Ask about this", recent activity).
  useEffect(() => {
    if (askDraft) {
      setText(askDraft);
      setAskDraft("");
      inputRef.current?.focus();
    }
  }, [askDraft, setAskDraft]);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
  }, [text]);

  const submit = () => {
    const value = text.trim();
    if (!value || isAsking) return;
    void ask(value);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const aiReady = overview.data?.ai.configured ?? true;
  const suggestions = overview.data?.suggestions ?? [];

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-6 sm:px-6">
          {turns.length === 0 ? (
            <EmptyState
              icon={Sparkles}
              title={`Ask anything about ${connection.label}`}
              description="Answers are generated as read-only SQL, checked by guardrails, run, and reviewed by a second model."
              action={
                suggestions.length > 0 && (
                  <div className="flex max-w-xl flex-wrap justify-center gap-2">
                    {suggestions.slice(0, 4).map((s) => (
                      <button
                        key={s}
                        type="button"
                        disabled={!aiReady}
                        onClick={() => void ask(s)}
                        className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-foreground/80 transition-colors hover:border-accent/40 hover:bg-accent/5 disabled:opacity-50"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )
              }
              className="py-20"
            />
          ) : (
            turns.map((turn) => <Turn key={turn.id} turn={turn} connection={connection} />)
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="shrink-0 border-t border-border bg-background px-4 py-3 sm:px-6">
        <div className="mx-auto w-full max-w-3xl">
          {!aiReady && (
            <p className="mb-2 text-xs text-warning">AI isn't configured on the backend (set GROQ_API_KEY), so questions can't be answered yet.</p>
          )}
          <div className="flex items-end gap-2 rounded-lg border border-border bg-card p-2 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
            <Textarea
              ref={inputRef}
              rows={1}
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX_LEN))}
              onKeyDown={onKeyDown}
              placeholder="Ask a question about your data…"
              aria-label="Your question"
              className="max-h-[150px] min-h-9 flex-1 border-0 bg-transparent py-1.5 focus:ring-0"
            />
            <Button variant="accent" size="icon" onClick={submit} disabled={!text.trim() || isAsking} aria-label="Send question">
              {isAsking ? <Spinner /> : <Send className="size-4" />}
            </Button>
          </div>
          <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>
              <Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> for a new line
            </span>
            <span className="flex items-center gap-3">
              {text.length > MAX_LEN * 0.8 && <span className="font-mono">{text.length}/{MAX_LEN}</span>}
              {turns.length > 0 && (
                <button type="button" onClick={clearChat} className="inline-flex items-center gap-1 hover:text-foreground">
                  <Trash2 className="size-3" />
                  New chat
                </button>
              )}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
