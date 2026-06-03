import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import type { TraceResult } from "@/lib/types";
import { formatMs } from "@/lib/utils";

/** Render the /api/trace/latest response as a Gantt-like chart. */
export function TraceChart({ trace }: { trace: TraceResult | null }) {
  if (!trace || !trace.spans.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Execution Trace</CardTitle>
        </CardHeader>
        <CardContent>
          <span className="text-xs text-[var(--color-text-muted)]">(no trace yet — run a moderation first)</span>
        </CardContent>
      </Card>
    );
  }

  const total = trace.spans.find((s) => s.span === "pipeline")?.dur_ms ?? Math.max(...trace.spans.map((s) => s.start_ms + s.dur_ms));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Execution Trace · <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{trace.case_id}</span>
        </CardTitle>
        <span className="text-[11px] text-[var(--color-text-muted)]">total {formatMs(total)}</span>
      </CardHeader>
      <CardContent>
        <div className="space-y-1.5">
          {trace.spans.map((s, i) => {
            const pct = total ? (s.dur_ms / total) * 100 : 0;
            const offset = total ? (s.start_ms / total) * 100 : 0;
            const isChild = s.span.startsWith("tool:") || ["build_session_manager", "build_graph", "graph.invoke_async"].includes(s.span);
            return (
              <div key={i} className="grid grid-cols-[180px_1fr_60px] items-center gap-3 text-[11px]">
                <span className={isChild ? "pl-4 text-[var(--color-text-muted)]" : "font-medium text-[var(--color-text)]"}>
                  {s.span}
                </span>
                <div className="relative h-3 rounded-full bg-[var(--color-panel-2)] border border-[var(--color-border)]">
                  <div
                    className="absolute top-0 h-full rounded-full bg-[var(--color-accent)] opacity-80"
                    style={{ left: `${offset}%`, width: `${Math.max(0.5, pct)}%` }}
                  />
                </div>
                <span className="text-right font-mono text-[var(--color-text-dim)]">{formatMs(s.dur_ms)}</span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
