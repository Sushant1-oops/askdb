import { Lock } from "lucide-react";
import { useMemo } from "react";

import type { QueryResult } from "@/lib/api";
import { formatCell, isNumericCell } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ResultsTable({
  result,
  className,
  showRowNumbers = true,
  startIndex = 0,
}: {
  result: QueryResult;
  className?: string;
  showRowNumbers?: boolean;
  startIndex?: number;
}) {
  const redacted = useMemo(() => new Set(result.redacted_columns), [result.redacted_columns]);
  const numericColumns = useMemo(() => {
    const set = new Set<string>();
    for (const col of result.columns) {
      const sample = result.rows.find((r) => r[col] !== null && r[col] !== undefined);
      if (sample && isNumericCell(sample[col])) set.add(col);
    }
    return set;
  }, [result.columns, result.rows]);

  if (result.rows.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-muted-foreground">The query ran successfully but returned no rows.</p>;
  }

  return (
    <div className={cn("overflow-auto", className)}>
      <table className="w-full border-collapse text-left text-[13px]">
        <thead className="sticky top-0 z-10 bg-muted">
          <tr>
            {showRowNumbers && <th className="w-10 border-b border-border px-3 py-2 text-right font-mono text-[10px] font-medium text-muted-foreground">#</th>}
            {result.columns.map((col) => (
              <th
                key={col}
                className={cn(
                  "whitespace-nowrap border-b border-border px-3 py-2 font-mono text-[11px] font-semibold text-foreground",
                  numericColumns.has(col) && "text-right",
                )}
              >
                <span className="inline-flex items-center gap-1">
                  {redacted.has(col) && <Lock className="size-3 text-warning" aria-label="Restricted column" />}
                  {col}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr key={i} className="border-b border-border/60 last:border-0 hover:bg-muted/50">
              {showRowNumbers && <td className="px-3 py-1.5 text-right font-mono text-[10px] text-muted-foreground">{startIndex + i + 1}</td>}
              {result.columns.map((col) => {
                const value = row[col];
                const isNull = value === null || value === undefined;
                const text = formatCell(value);
                return (
                  <td
                    key={col}
                    title={text.length > 40 ? text : undefined}
                    className={cn(
                      "max-w-[320px] truncate px-3 py-1.5",
                      numericColumns.has(col) && "text-right font-mono tabular-nums",
                      isNull && "font-mono text-[11px] italic text-muted-foreground/70",
                      redacted.has(col) && !isNull && "font-mono text-[11px] text-warning",
                    )}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
