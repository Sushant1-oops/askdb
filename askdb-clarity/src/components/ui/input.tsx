import * as React from "react";

import { cn } from "@/lib/utils";

const fieldClass =
  "w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-50";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(function Input(
  { className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(fieldClass, "h-9", className)} {...props} />;
});

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<"textarea">>(function Textarea(
  { className, ...props },
  ref,
) {
  return <textarea ref={ref} className={cn(fieldClass, "min-h-20 resize-none py-2 leading-relaxed", className)} {...props} />;
});

export { Input, Textarea, fieldClass };
