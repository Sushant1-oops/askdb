import { Check, Copy, Terminal } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const KEYWORDS =
  "SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|USING|AS|AND|OR|NOT|IN|IS|NULL|LIKE|ILIKE|BETWEEN|CASE|WHEN|THEN|ELSE|END|DISTINCT|UNION|ALL|INTERSECT|EXCEPT|WITH|RECURSIVE|OVER|PARTITION BY|ASC|DESC|EXISTS|COUNT|SUM|AVG|MIN|MAX|COALESCE|NULLIF|CAST|EXTRACT|INTERVAL|TRUE|FALSE";
const TOKEN = new RegExp(`(--[^\\n]*|/\\*[\\s\\S]*?\\*/)|('(?:[^']|'')*')|\\b(\\d+(?:\\.\\d+)?)\\b|\\b(${KEYWORDS})\\b`, "gi");

export function highlightSql(sql: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of sql.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    if (index > last) out.push(sql.slice(last, index));
    const [text, comment, string, number, keyword] = match;
    const cls = comment
      ? "text-muted-foreground italic"
      : string
        ? "text-warning"
        : number
          ? "text-chart-3"
          : keyword
            ? "font-semibold text-accent"
            : "";
    out.push(
      <span key={key++} className={cls}>
        {text}
      </span>,
    );
    last = index + text.length;
  }
  if (last < sql.length) out.push(sql.slice(last));
  return out;
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy to the clipboard");
    }
  };
  return (
    <Button variant="ghost" size="sm" onClick={() => void copy()} aria-label={label}>
      {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
      {copied ? "Copied" : label}
    </Button>
  );
}

export function SqlBlock({
  sql,
  title = "SQL",
  actions,
  className,
}: {
  sql: string;
  title?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-md border border-border", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted px-3 py-1">
        <span className="flex items-center gap-1.5 font-mono text-[11px] font-medium text-muted-foreground">
          <Terminal className="size-3" />
          {title}
        </span>
        <div className="flex items-center gap-1">
          {actions}
          <CopyButton text={sql} />
        </div>
      </div>
      <pre className="max-h-72 overflow-auto bg-card p-3 font-mono text-xs leading-5 text-foreground">
        <code>{highlightSql(sql)}</code>
      </pre>
    </div>
  );
}
