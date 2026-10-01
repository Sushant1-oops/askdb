import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Activity, Bot, Database, Menu, Table2, Terminal, Workflow, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ConnectionSwitcher } from "@/components/layout/connection-switcher";
import { Pill, StatusDot } from "@/components/common/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/state/workspace";

const NAV = [
  { to: "/", label: "Overview", icon: Activity },
  { to: "/ask", label: "Ask AI", icon: Bot },
  { to: "/sql", label: "SQL Editor", icon: Terminal },
  { to: "/schema", label: "Schema", icon: Workflow },
  { to: "/tables", label: "Tables", icon: Table2 },
  { to: "/connections", label: "Connections", icon: Database },
] as const;

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
        <Database className="size-4" />
      </span>
      <span className="font-display text-lg font-bold">AskDB</span>
    </Link>
  );
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          {...(to === "/" ? { activeOptions: { exact: true } } : {})}
          onClick={onNavigate}
          className="flex h-9 items-center gap-2.5 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground data-[status=active]:bg-accent/10 data-[status=active]:text-accent"
        >
          <Icon className="size-4" />
          {label}
        </Link>
      ))}
    </nav>
  );
}

function ApiStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000, retry: false });
  const online = health.isSuccess;
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs">
      <StatusDot tone={health.isPending ? "neutral" : online ? "success" : "danger"} />
      <div className="min-w-0">
        <p className="font-semibold">{health.isPending ? "Checking API…" : online ? "API online" : "API offline"}</p>
        <p className="truncate font-mono text-[10px] text-muted-foreground">{health.data ? `v${health.data.version}` : "check the backend"}</p>
      </div>
    </div>
  );
}

function AiStatus() {
  const status = useQuery({ queryKey: ["model-status"], queryFn: api.modelStatus, staleTime: 60_000, retry: false });
  if (!status.data) return null;
  return status.data.configured ? (
    <Pill tone="success" title={`Models: ${status.data.model_chain.join(" → ")}`}>AI ready</Pill>
  ) : (
    <Pill tone="warning" title="Set GROQ_API_KEY in the backend .env and restart">AI not configured</Pill>
  );
}

export function AppShell() {
  const { offline, refetchConnections } = useWorkspace();
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <aside className="hidden w-60 shrink-0 flex-col justify-between border-r border-border bg-card p-4 lg:flex">
        <div className="space-y-6">
          <Brand />
          <SidebarNav />
        </div>
        <ApiStatus />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button aria-label="Close menu" className="absolute inset-0 bg-foreground/30" onClick={() => setMobileOpen(false)} />
          <aside className="relative flex h-full w-64 flex-col justify-between border-r border-border bg-card p-4">
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <Brand />
                <Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => setMobileOpen(false)}>
                  <X className="size-4" />
                </Button>
              </div>
              <SidebarNav onNavigate={() => setMobileOpen(false)} />
            </div>
            <ApiStatus />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setMobileOpen(true)}>
            <Menu className="size-4" />
          </Button>
          <ConnectionSwitcher />
          <div className="ml-auto flex items-center gap-2">
            <AiStatus />
          </div>
        </header>

        {offline && (
          <div role="alert" className="flex items-center justify-between gap-3 border-b border-danger/30 bg-danger/5 px-4 py-2 text-sm">
            <span className="text-danger">Can't reach the AskDB backend. Make sure it is running, then retry.</span>
            <Button variant="outline" size="sm" onClick={refetchConnections}>
              Retry
            </Button>
          </div>
        )}

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageContainer({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("enter-rise mx-auto w-full max-w-[1280px] px-4 py-6 sm:px-8", className)}>{children}</div>;
}
