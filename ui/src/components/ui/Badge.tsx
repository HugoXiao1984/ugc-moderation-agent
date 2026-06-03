import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Tone = "neutral" | "ok" | "warn" | "danger" | "accent";

export function Badge({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  const toneClass: Record<Tone, string> = {
    neutral: "bg-[var(--color-panel-2)] text-[var(--color-text-dim)] border-[var(--color-border)]",
    ok: "bg-[color-mix(in_oklab,var(--color-ok)_15%,transparent)] text-[var(--color-ok)] border-[color-mix(in_oklab,var(--color-ok)_35%,transparent)]",
    warn: "bg-[color-mix(in_oklab,var(--color-warn)_15%,transparent)] text-[var(--color-warn)] border-[color-mix(in_oklab,var(--color-warn)_35%,transparent)]",
    danger:
      "bg-[color-mix(in_oklab,var(--color-danger)_15%,transparent)] text-[var(--color-danger)] border-[color-mix(in_oklab,var(--color-danger)_35%,transparent)]",
    accent:
      "bg-[color-mix(in_oklab,var(--color-accent)_15%,transparent)] text-[var(--color-accent)] border-[color-mix(in_oklab,var(--color-accent)_35%,transparent)]",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide",
        toneClass[tone],
        className
      )}
      {...props}
    />
  );
}

export function Dot({ tone = "neutral" }: { tone?: Tone }) {
  const bg: Record<Tone, string> = {
    neutral: "bg-[var(--color-text-muted)]",
    ok: "bg-[var(--color-ok)]",
    warn: "bg-[var(--color-warn)]",
    danger: "bg-[var(--color-danger)]",
    accent: "bg-[var(--color-accent)]",
  };
  return <span className={cn("inline-block size-1.5 rounded-full", bg[tone])} />;
}
