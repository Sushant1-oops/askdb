import { Link } from "@tanstack/react-router";
import { Database } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState, Spinner } from "@/components/common/ui";
import { Button } from "@/components/ui/button";
import type { Connection } from "@/lib/api";
import { useWorkspace } from "@/state/workspace";

export function RequireConnection({ children }: { children: (connection: Connection) => ReactNode }) {
  const { active, connectionsLoading, offline } = useWorkspace();

  if (connectionsLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Spinner className="size-5" />
      </div>
    );
  }
  if (!active) {
    return (
      <EmptyState
        icon={Database}
        title={offline ? "Can't reach the AskDB backend" : "Connect a database to get started"}
        description={
          offline
            ? "Start the API (python main.py) and reload this page."
            : "Use the demo database to explore AskDB instantly, or connect your own PostgreSQL, MySQL or SQLite database."
        }
        action={
          !offline && (
            <Button asChild variant="accent">
              <Link to="/connections">Connect a database</Link>
            </Button>
          )
        }
      />
    );
  }
  return <>{children(active)}</>;
}
