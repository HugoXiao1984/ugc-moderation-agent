import { cn } from "@/lib/utils";

export function Progress({ value, className }: { value: number; className?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-panel-2)] border border-[var(--color-border)]",
        className
      )}
    >
      <div
        className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-500"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
