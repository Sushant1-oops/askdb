import { Database, Sparkles, Upload } from "lucide-react";
import { useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { ErrorNotice, Spinner } from "@/components/common/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type ConnectPayload, type Connection, type DbType } from "@/lib/api";
import { DB_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/state/workspace";

const DEFAULT_PORTS: Record<DbType, string> = { sqlite: "", postgresql: "5432", mysql: "3306" };

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-foreground">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function ConnectPanel({ onConnected }: { onConnected?: (connection: Connection) => void }) {
  const { connectionAdded } = useWorkspace();
  const [dbType, setDbType] = useState<DbType>("sqlite");
  const [busy, setBusy] = useState<"demo" | "upload" | "form" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ filePath: "", host: "", port: "", database: "", username: "", password: "", ssl: false });
  const fileInput = useRef<HTMLInputElement>(null);

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }));

  const finish = (connection: Connection) => {
    connectionAdded(connection);
    toast.success(`Connected to ${connection.label}`);
    onConnected?.(connection);
  };

  const run = async (kind: "demo" | "upload" | "form", action: () => Promise<Connection>) => {
    setBusy(kind);
    setError(null);
    try {
      finish(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect.");
    } finally {
      setBusy(null);
    }
  };

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void run("upload", () => api.connectUpload(file));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const payload: ConnectPayload =
      dbType === "sqlite"
        ? { db_type: "sqlite", database: form.filePath.split(/[\\/]/).pop() ?? "", file_path: form.filePath.trim() }
        : {
            db_type: dbType,
            database: form.database.trim(),
            host: form.host.trim(),
            port: Number(form.port || DEFAULT_PORTS[dbType]),
            username: form.username.trim(),
            ...(form.password ? { password: form.password } : {}),
            ...(dbType === "postgresql" && form.ssl ? { ssl: true } : {}),
          };
    void run("form", () => api.connect(payload));
  };

  const disabled = busy !== null;

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => void run("demo", api.connectDemo)}
          className="group flex items-start gap-3 rounded-lg border border-accent/30 bg-accent/5 p-4 text-left transition-colors hover:bg-accent/10 disabled:opacity-60"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-accent text-accent-foreground">
            {busy === "demo" ? <Spinner /> : <Sparkles className="size-4" />}
          </span>
          <span>
            <span className="block font-display text-sm font-bold">Try the demo database</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">E-commerce sample (customers, orders, products). No setup needed.</span>
          </span>
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => fileInput.current?.click()}
          className="flex items-start gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors hover:bg-muted disabled:opacity-60"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-foreground">
            {busy === "upload" ? <Spinner /> : <Upload className="size-4" />}
          </span>
          <span>
            <span className="block font-display text-sm font-bold">Upload a SQLite file</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">.db, .sqlite or .sqlite3 — opened read-only.</span>
          </span>
        </button>
        <input ref={fileInput} type="file" accept=".db,.sqlite,.sqlite3" className="hidden" onChange={onFile} />
      </div>

      <div className="flex items-center gap-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        or connect with details
        <span className="h-px flex-1 bg-border" />
      </div>

      <form onSubmit={submit} className="space-y-4">
        <div className="inline-flex rounded-md border border-border bg-muted p-0.5" role="tablist" aria-label="Database type">
          {(Object.keys(DB_LABELS) as DbType[]).map((type) => (
            <button
              key={type}
              type="button"
              role="tab"
              aria-selected={dbType === type}
              onClick={() => {
                setDbType(type);
                setError(null);
              }}
              className={cn(
                "rounded px-3 py-1.5 text-xs font-semibold transition-colors",
                dbType === type ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {DB_LABELS[type]}
            </button>
          ))}
        </div>

        {dbType === "sqlite" ? (
          <Field label="File path on the server" hint="Absolute path, or relative to the backend's working directory.">
            <Input required placeholder="/data/shop.db" value={form.filePath} onChange={(e) => set("filePath", e.target.value)} />
          </Field>
        ) : (
          <div className="grid gap-3 sm:grid-cols-6">
            <div className="sm:col-span-4">
              <Field label="Host">
                <Input required placeholder="db.example.com" value={form.host} onChange={(e) => set("host", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Port">
                <Input inputMode="numeric" placeholder={DEFAULT_PORTS[dbType]} value={form.port} onChange={(e) => set("port", e.target.value.replace(/\D/g, ""))} />
              </Field>
            </div>
            <div className="sm:col-span-6">
              <Field label="Database">
                <Input required value={form.database} onChange={(e) => set("database", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-3">
              <Field label="Username">
                <Input required autoComplete="off" value={form.username} onChange={(e) => set("username", e.target.value)} />
              </Field>
            </div>
            <div className="sm:col-span-3">
              <Field label="Password">
                <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} />
              </Field>
            </div>
            {dbType === "postgresql" && (
              <label className="flex items-center gap-2 text-xs text-muted-foreground sm:col-span-6">
                <input type="checkbox" className="accent-[var(--accent)]" checked={form.ssl} onChange={(e) => set("ssl", e.target.checked)} />
                Require SSL (needed by most hosted databases)
              </label>
            )}
          </div>
        )}

        {error && <ErrorNotice title="Connection failed" message={error} />}

        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-muted-foreground">Sessions are read-only. Passwords are never stored or returned.</p>
          <Button type="submit" variant="accent" disabled={disabled}>
            {busy === "form" ? <Spinner /> : <Database className="size-4" />}
            Connect
          </Button>
        </div>
      </form>
    </div>
  );
}
