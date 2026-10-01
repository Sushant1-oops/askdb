import { CircleCheck, CircleX, Lock, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";

import { Pill } from "@/components/common/ui";
import { SqlBlock } from "@/components/query/sql-block";
import type { Attempt, Guardrails, JudgeInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const CRITERIA_LABELS: Record<string, string> = {
  schema_fidelity: "Schema fidelity",
  question_match: "Answers the question",
  result_plausibility: "Result plausibility",
  safety: "Safety",
};

const STAGE_LABELS: Record<Attempt["stage"], string> = {
  generate: "Generated",
  repair: "Auto-repaired",
  judge_revision: "Revised after review",
};

export function VerdictBadge({ judge, lowConfidence }: { judge: JudgeInfo; lowConfidence?: boolean | undefined }) {
  if (!judge.enabled) return <Pill title="AI review is turned off on the server">Unreviewed</Pill>;
  if (judge.verdict === "skipped") return <Pill title={judge.error}>Review unavailable</Pill>;
  const pct = judge.score !== null && judge.score !== undefined ? ` ${Math.round(judge.score * 100)}%` : "";
  if (judge.verdict === "pass" && !lowConfidence) {
    return <Pill tone="success" icon={ShieldCheck} title={judge.summary}>Verified{pct}</Pill>;
  }
  return <Pill tone="warning" icon={TriangleAlert} title={judge.summary}>Needs review{pct}</Pill>;
}

export function GuardrailPills({ guardrails }: { guardrails: Guardrails }) {
  return (
    <>
      <Pill icon={Lock} title="Only SELECT statements run; the session is read-only">Read-only</Pill>
      {guardrails.limit_applied && <Pill title={guardrails.warnings.find((w) => w.includes("LIMIT"))}>Row limit added</Pill>}
    </>
  );
}

export function JudgePanel({ judge }: { judge: JudgeInfo }) {
  if (!judge.enabled || judge.verdict === "skipped") {
    return <p className="text-sm text-muted-foreground">{judge.enabled ? (judge.error ?? "The reviewer was unavailable.") : "AI review is turned off."}</p>;
  }
  const criteria = Object.entries(judge.criteria ?? {});
  return (
    <div className="space-y-3 text-sm">
      {judge.summary && <p className="text-foreground/90">{judge.summary}</p>}
      {criteria.length > 0 && (
        <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {criteria.map(([key, value]) => (
            <div key={key}>
              <div className="flex justify-between text-[11px] text-muted-foreground">
                <span>{CRITERIA_LABELS[key] ?? key}</span>
                <span className="font-mono">{Math.round(value * 100)}%</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className={cn("h-full rounded-full", value >= 0.7 ? "bg-success" : value >= 0.4 ? "bg-warning" : "bg-danger")}
                  style={{ width: `${Math.round(value * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
      {judge.issues && judge.issues.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-foreground/80">
          {judge.issues.map((issue, i) => (
            <li key={i}>{issue}</li>
          ))}
        </ul>
      )}
      {judge.signals && judge.signals.length > 0 && (
        <p className="text-[11px] text-muted-foreground">Automatic checks: {judge.signals.join(" ")}</p>
      )}
      <p className="text-[11px] text-muted-foreground">
        Reviewed by <span className="font-mono">{judge.model ?? "reviewer model"}</span>
        {judge.revisions ? ` · ${judge.revisions} revision round` : ""}
      </p>
    </div>
  );
}

export function AttemptsTimeline({ attempts }: { attempts: Attempt[] }) {
  return (
    <ol className="space-y-3">
      {attempts.map((a) => (
        <li key={a.n} className="flex gap-3">
          <span className="mt-0.5">
            {a.outcome === "ok" ? (
              <CircleCheck className="size-4 text-success" />
            ) : a.outcome === "blocked" ? (
              <ShieldAlert className="size-4 text-warning" />
            ) : (
              <CircleX className="size-4 text-danger" />
            )}
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            <p className="text-sm font-medium">
              {a.n}. {STAGE_LABELS[a.stage]}
              <span className="ml-2 font-normal text-muted-foreground">
                {a.outcome === "ok" ? "ran successfully" : a.outcome === "blocked" ? "blocked by guardrails" : "failed"}
                {a.judge && a.judge.score !== null ? ` · reviewer ${Math.round(a.judge.score * 100)}% (${a.judge.verdict})` : ""}
              </span>
            </p>
            {a.detail && <p className="break-words text-[13px] text-danger">{a.detail}</p>}
            <SqlBlock sql={a.sql} title={`attempt ${a.n}`} />
          </div>
        </li>
      ))}
    </ol>
  );
}
