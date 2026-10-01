
export type DbType = "sqlite" | "postgresql" | "mysql";

export interface Connection {
  connection_id: string;
  db_type: DbType;
  database: string;
  label: string;
  host: string | null;
  port: number | null;
  username: string | null;
  created_at: string;
  status: string;
}

export type Cell = string | number | boolean | null | Cell[] | { [key: string]: Cell };
export type Row = Record<string, Cell>;

export interface QueryResult {
  success: boolean;
  columns: string[];
  rows: Row[];
  row_count: number;
  truncated: boolean;
  execution_ms: number;
  redacted_columns: string[];
}

export interface Violation {
  code: string;
  message: string;
  security: boolean;
}

export interface Guardrails {
  passed: boolean;
  violations: Violation[];
  warnings: string[];
  tables: string[];
  limit_applied: boolean;
  read_only: boolean;
}

export type Verdict = "pass" | "revise" | "fail" | "skipped";

export interface JudgeInfo {
  enabled: boolean;
  verdict?: Verdict;
  score?: number | null;
  criteria?: Record<string, number>;
  issues?: string[];
  suggestion?: string;
  summary?: string;
  model?: string;
  signals?: string[];
  revisions?: number;
  error?: string;
}

export interface Attempt {
  n: number;
  stage: "generate" | "repair" | "judge_revision";
  sql: string;
  outcome: "ok" | "blocked" | "error";
  detail: string;
  judge?: { verdict: string; score: number | null };
}

export interface ChartSpec {
  type: "bar" | "line" | "area" | "pie" | "scatter";
  title: string;
  xKey: string;
  yKeys: string[];
}

export type AskStatus = "success" | "blocked" | "failed" | "clarification";

export interface AskResponse {
  status: AskStatus;
  question: string;
  message: string;
  sql: string | null;
  result: QueryResult | null;
  guardrails: Guardrails;
  attempts: Attempt[];
  retries: number;
  timings: Record<string, number>;
  execution_time: number;
  assumptions: string[];
  judge: JudgeInfo;
  model_used: string | null;
  confidence?: number | null;
  low_confidence?: boolean;
  clarification_type?: "unanswerable" | "ambiguous";
  answer?: string;
  chart?: ChartSpec | null;
  follow_ups?: string[];
}

export interface SqlResponse {
  status: "success" | "blocked" | "failed";
  message: string;
  sql: string;
  result: QueryResult | null;
  guardrails: Guardrails | null;
  execution_time: number;
}

export interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  restricted: boolean;
}

export interface ForeignKey {
  columns: string[];
  ref_table: string;
  ref_columns: string[];
}

export interface SchemaTable {
  name: string;
  kind: "table" | "view";
  row_count: number | null;
  primary_keys: string[];
  columns: SchemaColumn[];
  foreign_keys: ForeignKey[];
}

export interface SchemaResponse {
  database: string;
  db_type: DbType;
  stats: { tables: number; views: number; columns: number; rows: number };
  tables: SchemaTable[];
}

export interface TableData extends QueryResult {
  table: string;
  total_rows: number | null;
  limit: number;
  offset: number;
}

export interface Overview {
  connection: Connection;
  status: "online" | "unreachable";
  latency_ms: number | null;
  stats: SchemaResponse["stats"];
  largest_tables: { name: string; row_count: number | null }[];
  usage: { total: number; succeeded: number; failed: number; today: number; avg_ms: number | null };
  suggestions: string[];
  ai: { configured: boolean; model: string | null; judge_enabled: boolean };
}

export interface HistoryItem {
  id: string;
  created_at: string;
  source: "ask" | "editor";
  question: string | null;
  sql: string | null;
  status: "success" | "failed" | "blocked" | "clarification";
  row_count: number | null;
  duration_ms: number | null;
  verdict: string | null;
}

export interface ModelStatus {
  configured: boolean;
  provider: string;
  model_chain: string[];
  judge_model_chain: string[];
  judge_enabled: boolean;
  limits: { max_rows: number; query_timeout_seconds: number; max_repair_attempts: number };
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sql?: string;
}

export interface ConnectPayload {
  db_type: DbType;
  database: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  file_path?: string;
  ssl?: boolean;
}

export type ExportFormat = "csv" | "excel" | "pdf";



export const API_BASE: string = (
  (import.meta.env["VITE_API_URL"] as string | undefined) ?? "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

    get isOffline(): boolean {
    return this.status === 0;
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((d: unknown) => (typeof d === "object" && d !== null && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join("; ");
    }
  } catch {
      }
  return `Request failed (${res.status})`;
}

async function send(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
    if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
    return res;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "The request timed out. Try a simpler question or check the backend.");
    }
    throw new ApiError(0, `Cannot reach the AskDB API at ${API_BASE}. Is the backend running?`);
  } finally {
    window.clearTimeout(timer);
  }
}

async function json<T>(path: string, init: RequestInit = {}, timeoutMs = 30_000): Promise<T> {
  const res = await send(path, init, timeoutMs);
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown, timeoutMs?: number): Promise<T> {
  return json<T>(
    path,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    timeoutMs,
  );
}

const enc = encodeURIComponent;
const AI_TIMEOUT = 120_000;

export const api = {
  health: () => json<{ status: string; version: string; ai_configured: boolean }>("/health", {}, 6_000),
  modelStatus: () => json<ModelStatus>("/api/query/model-status", {}, 10_000),

  listConnections: async () => (await json<{ connections: Connection[] }>("/api/database/connections")).connections,
  connect: (payload: ConnectPayload) => post<Connection>("/api/database/connect", payload, 60_000),
  connectDemo: () => post<Connection>("/api/database/connect-demo", {}, 60_000),
  connectUpload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return json<Connection>("/api/database/connect-upload", { method: "POST", body: form }, 120_000);
  },
  disconnect: (id: string) => json<{ status: string }>(`/api/database/connections/${enc(id)}`, { method: "DELETE" }),

  overview: (id: string) => json<Overview>(`/api/database/connections/${enc(id)}/overview`, {}, 60_000),
  schema: (id: string, refresh = false) =>
    json<SchemaResponse>(`/api/database/connections/${enc(id)}/schema${refresh ? "?refresh=true" : ""}`, {}, 60_000),
  tableData: (id: string, table: string, limit: number, offset: number) =>
    json<TableData>(
      `/api/database/connections/${enc(id)}/tables/${enc(table)}/data?limit=${limit}&offset=${offset}`,
      {},
      60_000,
    ),

  chat: (body: { connection_id: string; question: string; history?: ChatMessage[]; judge?: boolean }) =>
    post<AskResponse>("/api/query/chat", body, AI_TIMEOUT),
  naturalLanguage: (body: { connection_id: string; question: string; judge?: boolean }) =>
    post<AskResponse>("/api/query/natural-language", body, AI_TIMEOUT),
  runSql: (body: { connection_id: string; sql_query: string }) => post<SqlResponse>("/api/query/sql", body, 60_000),
  history: async (id: string, limit = 30) =>
    (await json<{ items: HistoryItem[] }>(`/api/query/history?connection_id=${enc(id)}&limit=${limit}`)).items,
  clearHistory: (id: string) => json<{ status: string }>(`/api/query/history?connection_id=${enc(id)}`, { method: "DELETE" }),
};

export interface DownloadedFile {
  blob: Blob;
  filename: string;
  truncated: boolean;
}

export async function downloadExport(
  kind: "query" | "table",
  body: Record<string, unknown>,
  fallbackName: string,
): Promise<DownloadedFile> {
  const res = await send(
    `/api/export/${kind}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    120_000,
  );
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  return {
    blob: await res.blob(),
    filename: match?.[1] ? decodeURIComponent(match[1]) : fallbackName,
    truncated: res.headers.get("X-Export-Truncated") === "true",
  };
}
