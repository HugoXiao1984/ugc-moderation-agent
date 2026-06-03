import { cn } from "@/lib/utils";

/**
 * Visual representation of the 6-node moderation Graph. Highlights the nodes
 * present in the given trace array.
 */
export function PipelineDiagram({ trace }: { trace: string[] }) {
  const active = new Set(trace);
  const node = (id: string, label: string, sub: string) => (
    <div
      className={cn(
        "flex flex-col gap-0.5 rounded-md border px-3 py-2 text-center transition",
        active.has(id)
          ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_14%,transparent)] shadow-[0_0_0_1px_color-mix(in_oklab,var(--color-accent)_40%,transparent)]"
          : "border-[var(--color-border)] bg-[var(--color-panel-2)] opacity-60"
      )}
    >
      <span className="text-[11px] font-semibold tracking-wide text-[var(--color-text)]">{label}</span>
      <span className="text-[9px] uppercase tracking-widest text-[var(--color-text-muted)]">{sub}</span>
    </div>
  );
  const arrow = (
    <span className="mx-1 text-[var(--color-text-muted)]">→</span>
  );
  return (
    <div className="flex flex-wrap items-center gap-y-3 text-xs">
      {node("orchestrator", "Orchestrator", "memory + router")}
      {arrow}
      {node("fast_screen", "FastScreen", "Rekognition")}
      {arrow}
      {node("deep_review", "DeepReview", "Nova Pro")}
      {arrow}
      {active.has("text_guard") && (
        <>
          {node("text_guard", "TextGuard", "Guardrail")}
          {arrow}
        </>
      )}
      {active.has("decision_heavy")
        ? node("decision_heavy", "Decision ⭑", "Sonnet 4.6")
        : node("decision_light", "Decision", "Haiku 4.5")}
    </div>
  );
}
