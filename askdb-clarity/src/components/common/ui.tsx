import type { LucideIcon } from "lucide-react";
import { LoaderCircle, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string | undefined;
  title: string;
  description?: string | undefined;
  actions?: ReactNode | undefined;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{eyebrow}</p>}
        <h1 className="mt-1 font-display text-2xl font-bold">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  icon: Icon,
  meta,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: string | undefined;
  icon?: LucideIcon | undefined;
  meta?: ReactNode | undefined;
  actions?: ReactNode | undefined;
  children: ReactNode;
  className?: string | undefined;
  bodyClassName?: string | undefined;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-card", className)}>
      {(title || actions || meta) && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {Icon && (
              <span className="grid size-6 shrink-0 place-items-center rounded-md bg-accent/10 text-accent">
                <Icon className="size-3.5" />
              </span>
            )}
            {title && <h2 className="truncate font-display text-sm font-bold">{title}</h2>}
            {meta && <span className="truncate font-mono text-[11px] text-muted-foreground">{meta}</span>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: string | undefined;
  action?: ReactNode | undefined;
  className?: string | undefined;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      <span className="grid size-11 place-items-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="size-5" />
      </span>
      <h3 className="mt-4 font-display text-base font-bold">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorNotice({ title = "Something went wrong", message, onRetry }: { title?: string | undefined; message: string; onRetry?: (() => void) | undefined }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 p-4">
      <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-danger">{title}</p>
        <p className="mt-0.5 break-words text-sm text-foreground/80">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string | undefined }) {
  return <LoaderCircle className={cn("size-4 animate-spin", className)} aria-hidden />;
}

export type Tone = "neutral" | "success" | "warning" | "danger" | "accent";

const toneClass: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  success: "bg-success/10 text-success",
  accent: "bg-accent/10 text-accent",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
};

export function Pill({ tone = "neutral", icon: Icon, children, title }: { tone?: Tone | undefined; icon?: LucideIcon | undefined; children: ReactNode; title?: string | undefined }) {
  return (
    <span
      title={title}
      className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold", toneClass[tone])}
    >
      {Icon && <Icon className="size-3" />}
      {children}
    </span>
  );
}

const dotClass: Record<Tone, string> = {
  neutral: "bg-muted-foreground/50",
  success: "bg-success",
  accent: "bg-accent",
  warning: "bg-warning",
  danger: "bg-danger",
};

export function StatusDot({ tone = "success", pulse = false }: { tone?: Tone | undefined; pulse?: boolean }) {
  return <span className={cn("size-2 shrink-0 rounded-full", dotClass[tone], pulse && "status-pulse")} aria-hidden />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{children}</kbd>;
}
