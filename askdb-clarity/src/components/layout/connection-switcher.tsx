import { useNavigate } from "@tanstack/react-router";
import { Check, ChevronDown, Database, Plus } from "lucide-react";

import { StatusDot } from "@/components/common/ui";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DB_LABELS } from "@/lib/format";
import { useWorkspace } from "@/state/workspace";

export function ConnectionSwitcher() {
  const { connections, active, selectConnection, offline } = useWorkspace();
  const navigate = useNavigate();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="max-w-[260px] justify-between" aria-label="Switch connection">
          <span className="flex min-w-0 items-center gap-2">
            <StatusDot tone={offline ? "danger" : active ? "success" : "neutral"} pulse={!!active && !offline} />
            <span className="truncate font-mono text-xs">{active ? active.label : "No database"}</span>
          </span>
          <ChevronDown className="size-3.5 shrink-0" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">Connections</DropdownMenuLabel>
        {connections.length === 0 && <p className="px-2 py-2 text-xs text-muted-foreground">Nothing connected yet.</p>}
        {connections.map((c) => (
          <DropdownMenuItem key={c.connection_id} onSelect={() => selectConnection(c.connection_id)} className="gap-2">
            <Database className="size-4 text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-mono text-xs">{c.label}</span>
              <span className="block text-[11px] text-muted-foreground">{DB_LABELS[c.db_type] ?? c.db_type}</span>
            </span>
            {active?.connection_id === c.connection_id && <Check className="size-4 text-accent" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void navigate({ to: "/connections" })} className="gap-2">
          <Plus className="size-4" />
          Add or manage connections
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
