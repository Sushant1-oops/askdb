import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ChevronDown, ChevronRight, Clock3, Eraser, Key, Lock, Play, Search, ShieldAlert, Sparkles, Table2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";

import { Kbd, Panel, Pill, Spinner } from "@/components/common/ui";
import { PageContainer } from "@/components/layout/app-shell";
import { RequireConnection } from "@/components/layout/require-connection";
import { ExportMenu } from "@/components/query/export-menu";
import { ResultsTable } from "@/components/query/results-table";
import { JudgePanel, VerdictBadge } from "@/components/query/trust";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type AskResponse, type Connection, type Guardrails, type JudgeInfo, type QueryResult, type SchemaTable } from "@/lib/api";
import { formatInt, formatMs, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/state/workspace";

export const Route = createFileRoute("/_app/sql")({
  head: () => ({ meta: [{ title: "SQL Editor — AskDB" }] }),
  component: () => <RequireConnection>{(connection) => <SqlEditor key={connection.connection_id} connection={connection} />}</RequireConnection>,
});

interface Output {
  status: "success" | "blocked" | "failed" | "clarification";
  message: string;
  sql: string;
  result: QueryResult | null;
  guardrails: Guardrails | null;
  seconds: number;
  source: "editor" | "ai";
  judge?: JudgeInfo;
  lowConfidence?: boolean | undefined;
  assumptions?: string[];
}

function SchemaExplorer({ tables, loading, onInsert }: { tables: SchemaTable[]; loading: boolean; onInsert: (text: string) => void }) {
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? tables.filter((t) => t.name.toLowerCase().includes(q) || t.columns.some((c) => c.name.toLowerCase().includes(q))) : tables;
  }, [tables, filter]);

  const toggle = (name: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  return (
    <Panel title="Schema" icon={Table2} className="flex min-h-0 flex-col" bodyClassName="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border p-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter tables & columns" className="h-8 pl-8 text-xs" aria-label="Filter schema" />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {loading && (
          <div className="space-y-2 p-2">
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
          </div>
        )}
        {!loading && shown.length === 0 && <p className="p-3 text-xs text-muted-foreground">No matches.</p>}
        {shown.map((t) => {
          const expanded = open.has(t.name) || filter.trim() !== "";
          return (
            <div key={t.name}>
              <div className="flex items-center rounded-md hover:bg-muted">
                <button type="button" onClick={() => toggle(t.name)} className="p-1.5 text-muted-foreground" aria-label={`${expanded ? "Collapse" : "Expand"} ${t.name}`}>
                  {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                </button>
                <button type="button" onClick={() => onInsert(t.name)} title="Insert table name" className="flex-1 truncate py-1.5 pr-2 text-left font-mono text-xs font-medium">
                  {t.name}
                </button>
                <span className="pr-2 font-mono text-[10px] text-muted-foreground">{formatInt(t.row_count)}</span>
              </div>
              {expanded && (
                <ul className="mb-1 ml-5 border-l border-border pl-2">
                  {t.columns.map((c) => (
                    <li key={c.name}>
                      <button
                        type="button"
                        disabled={c.restricted}
                        onClick={() => onInsert(c.name)}
                        title={c.restricted ? "Restricted column" : "Insert column name"}
                        className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {c.primary_key ? <Key className="size-3 text-warning" /> : c.restricted ? <Lock className="size-3 text-warning" /> : <span className="size-3" />}
                        <span className="flex-1 truncate font-mono">{c.name}</span>
                        <span className="truncate font-mono text-[10px] text-muted-foreground">{c.type.toLowerCase()}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function SqlEditor({ connection }: { connection: Connection }) {
  const id = connection.connection_id;
  const queryClient = useQueryClient();
  const { sqlDraft, setSqlDraft } = useWorkspace();
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const [running, setRunning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [output, setOutput] = useState<Output | null>(null);
  const [exportSql, setExportSql] = useState<string | null>(null);

  const schema = useQuery({ queryKey: ["schema", id], queryFn: () => api.schema(id), staleTime: 60_000 });
  const history = useQuery({ queryKey: ["history", id, 15], queryFn: () => api.history(id, 15) });
  const recent = (history.data ?? []).filter((h) => h.sql).slice(0, 10);
  const aiReady = useQuery({ queryKey: ["model-status"], queryFn: api.modelStatus, staleTime: 60_000, retry: false }).data?.configured ?? true;

  
  useEffect(() => {
    if (sqlDraft || !schema.data) return;
    const biggest = [...schema.data.tables].sort((a, b) => (b.row_count ?? 0) - (a.row_count ?? 0))[0];
    if (biggest) setSqlDraft(`SELECT *\nFROM ${biggest.name}\nLIMIT 50;`);
  }, [schema.data, sqlDraft, setSqlDraft]);

  const refreshActivity = () => {
    void queryClient.invalidateQueries({ queryKey: ["history", id] });
    void queryClient.invalidateQueries({ queryKey: ["overview", id] });
  };

  const run = async () => {
    const sql = sqlDraft.trim();
    if (!sql || running) return;
    setRunning(true);
    try {
      const res = await api.runSql({ connection_id: id, sql_query: sql });
      setOutput({ status: res.status, message: res.message, sql: res.sql, result: res.result, guardrails: res.guardrails, seconds: res.execution_time, source: "editor" });
      setExportSql(res.status === "success" ? sql : null);
    } catch (e) {
      setOutput({ status: "failed", message: e instanceof Error ? e.message : "Query failed", sql, result: null, guardrails: null, seconds: 0, source: "editor" });
      setExportSql(null);
    } finally {
      setRunning(false);
      refreshActivity();
    }
  };

  const generate = async () => {
    const question = prompt.trim();
    if (!question || generating) return;
    setGenerating(true);
    try {
      const res: AskResponse = await api.naturalLanguage({ connection_id: id, question });
      if (res.sql) setSqlDraft(res.sql);
      setOutput({
        status: res.status,
        message: res.message,
        sql: res.sql ?? "",
        result: res.result,
        guardrails: res.guardrails,
        seconds: res.execution_time,
        source: "ai",
        judge: res.judge,
        lowConfidence: res.low_confidence,
        assumptions: res.assumptions,
      });
      setExportSql(res.status === "success" && res.sql ? res.sql : null);
      if (res.status === "success") setPrompt("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not generate SQL");
    } finally {
      setGenerating(false);
      refreshActivity();
    }
  };

  const insertAtCursor = (text: string) => {
    const el = editorRef.current;
    if (!el) {
      setSqlDraft(`${sqlDraft}${text}`);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const next = `${sqlDraft.slice(0, start)}${text}${sqlDraft.slice(end)}`;
    setSqlDraft(next);
    window.requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + text.length, start + text.length);
    });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void run();
    } else if (e.key === "Tab") {
      e.preventDefault();
      insertAtCursor("  ");
    }
  };

  const lines = sqlDraft.split("\n").length;
  const result = output?.result ?? null;

  return (
    <PageContainer className="max-w-[1500px]">
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="hidden max-h-[calc(100dvh-8rem)] lg:flex lg:flex-col">
          <SchemaExplorer tables={schema.data?.tables ?? []} loading={schema.isPending} onInsert={insertAtCursor} />
        </aside>

        <div className="min-w-0 space-y-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void generate();
            }}
            className="flex gap-2 rounded-lg border border-border bg-card p-2.5"
          >
            <div className="relative flex-1">
              <Sparkles className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-accent" />
              <Input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={aiReady ? "Describe the data you want and let AI write the SQL…" : "AI isn't configured on the backend (GROQ_API_KEY)"}
                disabled={!aiReady}
                className="pl-9"
                aria-label="Describe the query you want"
                maxLength={1000}
              />
            </div>
            <Button type="submit" variant="outline" disabled={!prompt.trim() || generating || !aiReady}>
              {generating ? <Spinner /> : <Sparkles className="size-3.5" />}
              Generate
            </Button>
          </form>

          <Panel
            title="Query"
            meta={`${lines} line${lines === 1 ? "" : "s"}`}
            actions={
              <>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" disabled={recent.length === 0}>
                      <Clock3 className="size-3.5" />
                      Recent
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-80">
                    <DropdownMenuLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">Recent queries</DropdownMenuLabel>
                    {recent.map((h) => (
                      <DropdownMenuItem key={h.id} onSelect={() => h.sql && setSqlDraft(h.sql)} className="flex-col items-start gap-0.5">
                        <span className="w-full truncate text-xs font-medium">{h.question ?? h.sql}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {h.source === "ask" ? "Ask AI" : "Editor"} · {h.status} · {timeAgo(h.created_at)}
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button variant="ghost" size="sm" onClick={() => setSqlDraft("")} disabled={!sqlDraft}>
                  <Eraser className="size-3.5" />
                  Clear
                </Button>
                <Button variant="accent" size="sm" onClick={() => void run()} disabled={!sqlDraft.trim() || running}>
                  {running ? <Spinner className="size-3.5" /> : <Play className="size-3.5" />}
                  Run
                </Button>
              </>
            }
          >
            <textarea
              ref={editorRef}
              value={sqlDraft}
              onChange={(e) => setSqlDraft(e.target.value)}
              onKeyDown={onKeyDown}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              aria-label="SQL query"
              placeholder="SELECT * FROM your_table LIMIT 50;"
              className="block min-h-48 w-full resize-y bg-card p-4 font-mono text-[13px] leading-6 text-foreground outline-none placeholder:text-muted-foreground"
            />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Lock className="size-3" /> Read-only · one statement · results capped and sensitive columns masked
              </span>
              <span>
                <Kbd>⌘</Kbd>/<Kbd>Ctrl</Kbd> + <Kbd>Enter</Kbd> to run
              </span>
            </div>
          </Panel>

          {(running || generating) && (
            <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground" role="status">
              <Spinner className="text-accent" /> {generating ? "Generating, running and reviewing SQL…" : "Running query…"}
            </div>
          )}

          {output && !running && !generating && (
            <Panel
              title="Results"
              meta={
                output.status === "success" && result
                  ? `${formatInt(result.row_count)} row${result.row_count === 1 ? "" : "s"} · ${formatMs(result.execution_ms)}${result.truncated ? " · row limit reached" : ""}`
                  : undefined
              }
              actions={
                <>
                  {output.source === "ai" && output.judge && <VerdictBadge judge={output.judge} lowConfidence={output.lowConfidence} />}
                  <ExportMenu
                    disabled={!result || result.row_count === 0}
                    source={exportSql ? { kind: "query", body: { connection_id: id, sql_query: exportSql }, name: "sql_results" } : null}
                  />
                </>
              }
            >
              {output.status === "success" && result ? (
                <>
                  {(result.redacted_columns.length > 0 || output.guardrails?.limit_applied || (output.assumptions?.length ?? 0) > 0) && (
                    <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-4 py-2">
                      {result.redacted_columns.length > 0 && <Pill tone="warning" icon={Lock}>Masked: {result.redacted_columns.join(", ")}</Pill>}
                      {output.guardrails?.limit_applied && <Pill>Row limit added</Pill>}
                      {output.assumptions?.map((a) => (
                        <Pill key={a} tone="accent">Assumed: {a}</Pill>
                      ))}
                    </div>
                  )}
                  <ResultsTable result={result} className="max-h-[28rem]" />
                  {output.source === "ai" && output.judge && output.judge.enabled && output.judge.verdict !== "pass" && (
                    <div className="border-t border-border p-4">
                      <JudgePanel judge={output.judge} />
                    </div>
                  )}
                </>
              ) : (
                <div className={cn("flex gap-3 p-4", output.status === "blocked" ? "bg-warning/5" : "bg-danger/5")} role="alert">
                  <ShieldAlert className={cn("mt-0.5 size-4 shrink-0", output.status === "blocked" ? "text-warning" : "text-danger")} />
                  <div className="min-w-0 space-y-1 text-sm">
                    <p className={cn("font-semibold", output.status === "blocked" ? "text-warning" : "text-danger")}>
                      {output.status === "blocked" ? "Blocked by guardrails" : output.status === "clarification" ? "Needs more detail" : "Query failed"}
                    </p>
                    <p className="break-words text-foreground/80">{output.message || "The query could not be run."}</p>
                  </div>
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </PageContainer>
  );
}
