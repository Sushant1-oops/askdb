import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Check, Database, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, Panel, Pill, Spinner, StatusDot } from "@/components/common/ui";
import { PageContainer } from "@/components/layout/app-shell";
import { ConnectPanel } from "@/components/connect/connect-panel";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { DB_LABELS, timeAgo } from "@/lib/format";
import { useWorkspace } from "@/state/workspace";

export const Route = createFileRoute("/_app/connections")({
  head: () => ({ meta: [{ title: "Connections — AskDB" }] }),
  component: Connections,
});

function Connections() {
  const navigate = useNavigate();
  const { connections, active, selectConnection, connectionRemoved, connectionsLoading } = useWorkspace();
  const [removing, setRemoving] = useState<string | null>(null);

  const disconnect = async (id: string, label: string) => {
    if (!window.confirm(`Disconnect from ${label}? Its chat and query history will be cleared.`)) return;
    setRemoving(id);
    try {
      await api.disconnect(id);
    } catch (e) {
      
      if (!(e instanceof Error) || !/not found/i.test(e.message)) {
        toast.error(e instanceof Error ? e.message : "Could not disconnect");
        setRemoving(null);
        return;
      }
    }
    connectionRemoved(id);
    setRemoving(null);
    toast.success(`Disconnected from ${label}`);
  };

  return (
    <PageContainer>
      <div className="mb-5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Workspace</p>
        <h1 className="mt-1 font-display text-2xl font-bold">Connections</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          AskDB opens every database read-only. Connections live in the backend's memory and are cleared when it restarts.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <Panel title="Active connections" icon={Database}>
            {connectionsLoading ? (
              <div className="flex justify-center p-8 text-muted-foreground">
                <Spinner className="size-5" />
              </div>
            ) : connections.length === 0 ? (
              <EmptyState icon={Database} title="Nothing connected" description="Add a database on the right." className="py-10" />
            ) : (
              <ul className="divide-y divide-border">
                {connections.map((c) => {
                  const isActive = active?.connection_id === c.connection_id;
                  return (
                    <li key={c.connection_id} className="flex items-center gap-3 px-5 py-3">
                      <StatusDot tone="success" pulse={isActive} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-sm font-semibold">{c.label}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {DB_LABELS[c.db_type] ?? c.db_type}
                          {c.host ? ` · ${c.host}${c.port ? `:${c.port}` : ""}` : ""} · {timeAgo(c.created_at)}
                        </p>
                      </div>
                      {isActive ? (
                        <Pill tone="accent" icon={Check}>Active</Pill>
                      ) : (
                        <Button variant="outline" size="sm" onClick={() => selectConnection(c.connection_id)}>
                          Use
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        aria-label={`Disconnect ${c.label}`}
                        disabled={removing === c.connection_id}
                        onClick={() => void disconnect(c.connection_id, c.label)}
                      >
                        {removing === c.connection_id ? <Spinner className="size-3.5" /> : <Trash2 className="size-3.5" />}
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </div>

        <div className="lg:col-span-3">
          <Panel title="Add a connection" icon={Database} bodyClassName="p-5">
            <ConnectPanel onConnected={() => void navigate({ to: "/" })} />
          </Panel>
        </div>
      </div>
    </PageContainer>
  );
}
