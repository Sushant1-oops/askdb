import { Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Spinner } from "@/components/common/ui";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { downloadExport, type ExportFormat } from "@/lib/api";
import { saveBlob } from "@/lib/format";

export interface ExportSource {
  kind: "query" | "table";
    body: Record<string, unknown>;
  name: string;
}

const FORMATS: { id: ExportFormat; label: string; ext: string }[] = [
  { id: "csv", label: "CSV", ext: "csv" },
  { id: "excel", label: "Excel (.xlsx)", ext: "xlsx" },
  { id: "pdf", label: "PDF", ext: "pdf" },
];

export function ExportMenu({ source, disabled }: { source: ExportSource | null; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);

  const run = async (format: ExportFormat, ext: string) => {
    if (!source) return;
    setBusy(true);
    try {
      const file = await downloadExport(source.kind, { ...source.body, format }, `${source.name}.${ext}`);
      saveBlob(file.blob, file.filename);
      toast.success(file.truncated ? `Exported ${file.filename} (row limit reached)` : `Exported ${file.filename}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled || busy || !source}>
          {busy ? <Spinner className="size-3.5" /> : <Download className="size-3.5" />}
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {FORMATS.map((f) => (
          <DropdownMenuItem key={f.id} onSelect={() => void run(f.id, f.ext)}>
            {f.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
