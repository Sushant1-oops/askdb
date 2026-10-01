import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Activity, Bot, Clock3, Columns3, Database, RefreshCw, Rows3, Send, Sparkles, Table2, TriangleAlert } from "lucide-react";
import { useState, type FormEvent } from "react";

import { EmptyState, ErrorNotice, Panel, Pill, StatusDot } from "@/components/common/ui";
import { PageContainer } from "@/components/layout/app-shell";
import { RequireConnection } from "@/components/layout/require-connection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Connection, type HistoryItem } from "@/lib/api";
import { DB_LABELS, formatCompact, formatInt, formatMs, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/state/workspace";

export const Route = createFileRoute("/_app/")({
  head: () => ({ meta: [{ title: "Overview — AskDB" }] }),
  component: () => (
    <RequireConnection>{(connection) => <Overview connection={connection} />}</RequireConnection>
  ),
});

function StatCard({ icon: Icon, label, value, hint, loading }: { icon: typeof Activity; label: string; value: string; hint?: string | undefined; loading: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="text-[11px] font-semibold uppercase tracking-wide">{label}</span>
        <Icon className="size-4" />
      </div>
      {loading ? <Skeleton className="mt-3 h-7 w-24" /> : <p className="mt-2 font-display text-2xl font-bold tabular-nums">{value}</p>}
      {hint && !loading && <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

const STATUS_TONE = { success: "success", failed: "danger", blocked: "warning", clarification: "neutral" } as const;

function ActivityRow({ item, onOpen }: { item: HistoryItem; onOpen: (item: HistoryItem) => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item)}
        className="flex w-full items-start gap-3 px-5 py-3 text-left transition-colors hover:bg-muted/60"
      >
        <span className="mt-1.5">
          <StatusDot tone={STATUS_TONE[item.status]} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{item.question ?? item.sql ?? "Query"}</span>
          <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground">
            {item.source === "ask" ? "Ask AI" : "SQL editor"}
            {item.row_count !== null ? ` · ${formatInt(item.row_count)} rows` : ""}
            {item.duration_ms !== null ? ` · ${formatMs(item.duration_ms)}` : ""}
          </span>
        </span>
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{timeAgo(item.created_at)}</span>
      </button>
    </li>
  );
}

function Overview({ connection }: { connection: Connection }) {
  const id = connection.connection_id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { ask, setAskDraft, setSqlDraft, refetchConnections } = useWorkspace();
  const [question, setQuestion] = useState("");

  const overview = useQuery({ queryKey: ["overview", id], queryFn: () => api.overview(id), refetchInterval: 60_000 });
  const history = useQuery({ queryKey: ["history", id, 8], queryFn: () => api.history(id, 8) });

  const startAsking = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    void ask(trimmed);
    setQuestion("");
    void navigate({ to: "/ask" });
  };

  const openHistory = (item: HistoryItem) => {
    if (item.source === "ask" && item.question) {
      setAskDraft(item.question);
      void navigate({ to: "/ask" });
    } else if (item.sql) {
      setSqlDraft(item.sql);
      void navigate({ to: "/sql" });
    }
  };

  const data = overview.data;
  const loading = overview.isPending;
  const maxRows = Math.max(1, ...(data?.largest_tables.map((t) => t.row_count ?? 0) ?? [1]));

  return (
    <PageContainer>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <StatusDot tone={data ? (data.status === "online" ? "success" : "danger") : "neutral"} pulse={data?.status === "online"} />
            {DB_LABELS[connection.db_type] ?? connection.db_type}
            {data?.latency_ms != null && <span className="font-mono normal-case">· {formatMs(data.latency_ms)} latency</span>}
          </p>
          <h1 className="mt-1 font-display text-2xl font-bold">{connection.label}</h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void queryClient.invalidateQueries({ queryKey: ["overview", id] });
            void queryClient.invalidateQueries({ queryKey: ["history", id] });
          }}
        >
          <RefreshCw className={cn("size-3.5", overview.isFetching && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {overview.isError && (
        <div className="mb-5">
          <ErrorNotice
            title="Couldn't load the overview"
            message={overview.error.message}
            onRetry={() => {
              void overview.refetch();
              refetchConnections();
            }}
          />
        </div>
      )}

      {data && !data.ai.configured && (
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-warning/30 bg-warning/5 p-4 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
          <p className="text-foreground/80">
            <span className="font-semibold text-warning">AI is not configured.</span> Add <code className="rounded bg-muted px-1 font-mono text-xs">GROQ_API_KEY</code> to the backend{" "}
            <code className="rounded bg-muted px-1 font-mono text-xs">.env</code> and restart. The SQL editor, schema and table browser work without it.
          </p>
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          startAsking(question);
        }}
        className="mb-5 flex gap-2 rounded-lg border border-border bg-card p-3"
      >
        <div className="relative flex-1">
          <Sparkles className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-accent" />
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask anything about your data…"
            className="h-10 pl-9"
            aria-label="Ask a question"
            maxLength={1000}
          />
        </div>
        <Button type="submit" variant="accent" className="h-10" disabled={!question.trim()}>
          <Send className="size-4" />
          Ask
        </Button>
      </form>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Table2} label="Tables" loading={loading} value={formatInt(data?.stats.tables)} hint={data && data.stats.views ? `+ ${data.stats.views} views` : "in this database"} />
        <StatCard icon={Rows3} label="Total rows" loading={loading} value={formatCompact(data?.stats.rows)} hint={data ? `${formatInt(data.stats.rows)} across all tables` : undefined} />
        <StatCard icon={Columns3} label="Columns" loading={loading} value={formatInt(data?.stats.columns)} />
        <StatCard
          icon={Clock3}
          label="Queries today"
          loading={loading}
          value={formatInt(data?.usage.today)}
          hint={data?.usage.avg_ms != null ? `avg ${formatMs(data.usage.avg_ms)} · ${data.usage.failed} failed` : "this session"}
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-3">
          <Panel
            title="Suggested questions"
            icon={Sparkles}
            actions={data && <Pill tone={data.ai.configured ? "success" : "warning"}>{data.ai.configured ? "AI ready" : "AI off"}</Pill>}
            bodyClassName="p-3"
          >
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-9" />
                <Skeleton className="h-9" />
                <Skeleton className="h-9" />
              </div>
            ) : data && data.suggestions.length > 0 ? (
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {data.suggestions.map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      disabled={!data.ai.configured}
                      onClick={() => startAsking(s)}
                      className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-left text-[13px] transition-colors hover:border-accent/40 hover:bg-accent/5 disabled:opacity-50"
                    >
                      <Bot className="size-3.5 shrink-0 text-accent" />
                      <span className="line-clamp-2">{s}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-2 py-4 text-sm text-muted-foreground">No suggestions yet for this schema.</p>
            )}
          </Panel>

          <Panel title="Largest tables" icon={Table2} bodyClassName="px-5 py-4">
            {loading ? (
              <Skeleton className="h-24" />
            ) : data && data.largest_tables.length > 0 ? (
              <ul className="space-y-3">
                {data.largest_tables.map((t) => (
                  <li key={t.name}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="font-mono font-medium">{t.name}</span>
                      <span className="font-mono text-muted-foreground">{formatInt(t.row_count)}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(2, ((t.row_count ?? 0) / maxRows) * 100)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No row counts available.</p>
            )}
          </Panel>
        </div>

        <Panel
          title="Recent activity"
          icon={Activity}
          className="lg:col-span-2"
          actions={
            <Button asChild variant="ghost" size="sm">
              <Link to="/sql">SQL editor</Link>
            </Button>
          }
        >
          {history.isPending ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : history.data && history.data.length > 0 ? (
            <ul className="divide-y divide-border">
              {history.data.map((item) => (
                <ActivityRow key={item.id} item={item} onOpen={openHistory} />
              ))}
            </ul>
          ) : (
            <EmptyState icon={Database} title="No queries yet" description="Ask a question or run SQL — it will show up here." className="py-10" />
          )}
        </Panel>
      </div>
    </PageContainer>
  );
}
