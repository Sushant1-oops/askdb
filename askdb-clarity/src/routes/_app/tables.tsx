import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, Lock, Search, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorNotice, Panel, Pill, Spinner } from "@/components/common/ui";
import { PageContainer } from "@/components/layout/app-shell";
import { RequireConnection } from "@/components/layout/require-connection";
import { ExportMenu } from "@/components/query/export-menu";
import { ResultsTable } from "@/components/query/results-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Connection } from "@/lib/api";
import { formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/state/workspace";

export const Route = createFileRoute("/_app/tables")({
  head: () => ({ meta: [{ title: "Tables — AskDB" }] }),
  component: () => <RequireConnection>{(connection) => <TableBrowser key={connection.connection_id} connection={connection} />}</RequireConnection>,
});

const PAGE_SIZE = 50;

function TableBrowser({ connection }: { connection: Connection }) {
  const id = connection.connection_id;
  const { tableFocus, setTableFocus } = useWorkspace();
  const [selected, setSelected] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");

  const schema = useQuery({ queryKey: ["schema", id], queryFn: () => api.schema(id), staleTime: 60_000 });
  const tables = schema.data?.tables ?? [];

  
  useEffect(() => {
    if (tableFocus && tables.some((t) => t.name === tableFocus)) {
      setSelected(tableFocus);
      setPage(0);
      setTableFocus(null);
    } else if (!selected && tables[0]) {
      setSelected(tables[0].name);
    }
  }, [tableFocus, tables, selected, setTableFocus]);

  const data = useQuery({
    queryKey: ["table", id, selected, page],
    queryFn: () => api.tableData(id, selected ?? "", PAGE_SIZE, page * PAGE_SIZE),
    enabled: selected !== null,
    placeholderData: (previous) => previous,
  });

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? tables.filter((t) => t.name.toLowerCase().includes(q)) : tables;
  }, [tables, filter]);

  const total = data.data?.total_rows ?? null;
  const pageCount = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;
  const hasNext = pageCount !== null ? page + 1 < pageCount : (data.data?.row_count ?? 0) === PAGE_SIZE;
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = page * PAGE_SIZE + (data.data?.row_count ?? 0);

  return (
    <PageContainer className="max-w-[1500px]">
      <div className="mb-5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{connection.label}</p>
        <h1 className="mt-1 font-display text-2xl font-bold">Tables</h1>
      </div>

      {schema.isError && <ErrorNotice title="Couldn't load tables" message={schema.error.message} onRetry={() => void schema.refetch()} />}

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <Panel bodyClassName="p-1.5" className="max-h-[calc(100dvh-12rem)] overflow-hidden lg:self-start">
          <div className="border-b border-border p-1.5">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter tables" className="h-8 pl-8 text-xs" aria-label="Filter tables" />
            </div>
          </div>
          <ul className="max-h-[calc(100dvh-17rem)] overflow-y-auto pt-1">
            {schema.isPending && (
              <li className="space-y-2 p-2">
                <Skeleton className="h-7" />
                <Skeleton className="h-7" />
              </li>
            )}
            {visible.map((t) => (
              <li key={t.name}>
                <button
                  type="button"
                  onClick={() => {
                    setSelected(t.name);
                    setPage(0);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left transition-colors hover:bg-muted",
                    selected === t.name && "bg-accent/10 text-accent hover:bg-accent/10",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Table2 className="size-3.5 shrink-0" />
                    <span className="truncate font-mono text-xs font-medium">{t.name}</span>
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">{formatInt(t.row_count)}</span>
                </button>
              </li>
            ))}
            {!schema.isPending && visible.length === 0 && <li className="p-3 text-xs text-muted-foreground">No tables found.</li>}
          </ul>
        </Panel>

        <div className="min-w-0">
          {selected === null ? (
            !schema.isPending && <EmptyState icon={Table2} title="Select a table" description="Pick a table on the left to preview its rows." />
          ) : (
            <Panel
              title={selected}
              icon={Table2}
              meta={total !== null ? `${formatInt(total)} rows` : undefined}
              actions={
                <>
                  {data.isFetching && <Spinner className="text-muted-foreground" />}
                  <ExportMenu source={{ kind: "table", body: { connection_id: id, table_name: selected }, name: selected }} disabled={total === 0} />
                </>
              }
            >
              {data.isError ? (
                <div className="p-4">
                  <ErrorNotice title="Couldn't load rows" message={data.error.message} onRetry={() => void data.refetch()} />
                </div>
              ) : data.data ? (
                <>
                  {data.data.redacted_columns.length > 0 && (
                    <div className="flex items-center gap-1.5 border-b border-border px-4 py-2">
                      <Pill tone="warning" icon={Lock}>Masked: {data.data.redacted_columns.join(", ")}</Pill>
                    </div>
                  )}
                  <ResultsTable result={data.data} className="max-h-[calc(100dvh-20rem)]" startIndex={page * PAGE_SIZE} />
                  <div className="flex items-center justify-between border-t border-border px-4 py-2.5">
                    <span className="font-mono text-xs text-muted-foreground">
                      {data.data.row_count === 0 ? "No rows" : `${formatInt(from)}–${formatInt(to)}${total !== null ? ` of ${formatInt(total)}` : ""}`}
                    </span>
                    <div className="flex items-center gap-1">
                      <Button variant="outline" size="sm" disabled={page === 0 || data.isFetching} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                        <ChevronLeft className="size-3.5" />
                        Prev
                      </Button>
                      <Button variant="outline" size="sm" disabled={!hasNext || data.isFetching} onClick={() => setPage((p) => p + 1)}>
                        Next
                        <ChevronRight className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="space-y-2 p-4">
                  <Skeleton className="h-8" />
                  <Skeleton className="h-8" />
                  <Skeleton className="h-8" />
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </PageContainer>
  );
}
