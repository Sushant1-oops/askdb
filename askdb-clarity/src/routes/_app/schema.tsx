import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowRight, Bot, Key, Lock, RefreshCw, Rows3, Search, Table2 } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState, ErrorNotice, Pill } from "@/components/common/ui";
import { PageContainer } from "@/components/layout/app-shell";
import { RequireConnection } from "@/components/layout/require-connection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Connection, type SchemaTable } from "@/lib/api";
import { formatInt } from "@/lib/format";
import { useWorkspace } from "@/state/workspace";

export const Route = createFileRoute("/_app/schema")({
  head: () => ({ meta: [{ title: "Schema — AskDB" }] }),
  component: () => <RequireConnection>{(connection) => <SchemaView key={connection.connection_id} connection={connection} />}</RequireConnection>,
});

function TableCard({ table, defaultOpen }: { table: SchemaTable; defaultOpen: boolean }) {
  const navigate = useNavigate();
  const { setAskDraft, setTableFocus } = useWorkspace();
  const fkColumns = new Set(table.foreign_keys.flatMap((fk) => fk.columns));

  return (
    <details open={defaultOpen} className="group rounded-lg border border-border bg-card">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-5 py-3 [&::-webkit-details-marker]:hidden">
        <Table2 className="size-4 text-accent" />
        <span className="font-mono text-sm font-semibold">{table.name}</span>
        {table.kind === "view" && <Pill>view</Pill>}
        <span className="font-mono text-[11px] text-muted-foreground">
          {table.columns.length} columns · {formatInt(table.row_count)} rows
        </span>
        <span className="ml-auto flex gap-1.5" onClick={(e) => e.preventDefault()}>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setTableFocus(table.name);
              void navigate({ to: "/tables" });
            }}
          >
            <Rows3 className="size-3.5" />
            Browse
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setAskDraft(`Give me an overview of the ${table.name.replace(/_/g, " ")} data`);
              void navigate({ to: "/ask" });
            }}
          >
            <Bot className="size-3.5" />
            Ask AI
          </Button>
        </span>
      </summary>

      <div className="border-t border-border">
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-muted-foreground">
              <th className="px-5 py-2 font-semibold">Column</th>
              <th className="px-3 py-2 font-semibold">Type</th>
              <th className="px-3 py-2 font-semibold">Flags</th>
            </tr>
          </thead>
          <tbody>
            {table.columns.map((c) => (
              <tr key={c.name} className="border-t border-border/60">
                <td className="px-5 py-1.5 font-mono text-xs font-medium">{c.name}</td>
                <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">{c.type.toLowerCase() || "—"}</td>
                <td className="px-3 py-1.5">
                  <span className="flex flex-wrap gap-1">
                    {c.primary_key && <Pill tone="warning" icon={Key}>PK</Pill>}
                    {fkColumns.has(c.name) && <Pill tone="accent">FK</Pill>}
                    {!c.nullable && !c.primary_key && <Pill>NOT NULL</Pill>}
                    {c.restricted && <Pill tone="warning" icon={Lock} title="Hidden from the AI and masked in results">restricted</Pill>}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {table.foreign_keys.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-2.5 text-xs text-muted-foreground">
            <span className="font-semibold">References</span>
            {table.foreign_keys.map((fk) => (
              <span key={`${fk.columns.join(",")}-${fk.ref_table}`} className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 font-mono">
                {fk.columns.join(", ")} <ArrowRight className="size-3" /> {fk.ref_table}({fk.ref_columns.join(", ")})
              </span>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

function SchemaView({ connection }: { connection: Connection }) {
  const id = connection.connection_id;
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const schema = useQuery({ queryKey: ["schema", id], queryFn: () => api.schema(id), staleTime: 60_000 });

  const tables = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const all = schema.data?.tables ?? [];
    return q ? all.filter((t) => t.name.toLowerCase().includes(q) || t.columns.some((c) => c.name.toLowerCase().includes(q))) : all;
  }, [schema.data, filter]);

  const refresh = async () => {
    const fresh = await api.schema(id, true);
    queryClient.setQueryData(["schema", id], fresh);
    void queryClient.invalidateQueries({ queryKey: ["overview", id] });
  };

  const stats = schema.data?.stats;

  return (
    <PageContainer>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{connection.label}</p>
          <h1 className="mt-1 font-display text-2xl font-bold">Schema</h1>
          {stats && (
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              {stats.tables} tables{stats.views ? ` · ${stats.views} views` : ""} · {formatInt(stats.columns)} columns · {formatInt(stats.rows)} rows
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter tables & columns" className="w-60 pl-8" aria-label="Filter schema" />
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()} title="Re-read the schema from the database">
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {schema.isError && <ErrorNotice title="Couldn't load the schema" message={schema.error.message} onRetry={() => void schema.refetch()} />}
      {schema.isPending && (
        <div className="space-y-3">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      )}
      {schema.data && tables.length === 0 && (
        <EmptyState icon={Table2} title={filter ? "No matching tables" : "This database has no tables"} description={filter ? "Try a different search." : undefined} />
      )}
      <div className="space-y-3">
        {tables.map((t) => (
          <TableCard key={t.name} table={t} defaultOpen={tables.length <= 4} />
        ))}
      </div>
    </PageContainer>
  );
}
