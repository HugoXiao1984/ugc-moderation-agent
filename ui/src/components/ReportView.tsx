import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { DecisionBadge } from "@/components/DecisionBadge";
import { FlagBadge, TagChips } from "@/components/FlagBadge";
import { PipelineDiagram } from "@/components/PipelineDiagram";
import type { ModerationReport } from "@/lib/types";

export function ReportView({ report, compact = false }: { report: ModerationReport; compact?: boolean }) {
  const d = report.decision;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <DecisionBadge decision={d.decision} />
        <FlagBadge flag={d.flag} />
        <Badge tone="neutral">{report.jurisdiction}</Badge>
        <Badge tone="accent">confidence {Math.round((d.confidence ?? 0) * 100)}%</Badge>
        {d.execution_mode && (
          <Badge tone="neutral" className="font-mono text-[10px]">
            {d.execution_mode}
          </Badge>
        )}
      </div>
      <TagChips tags={d.tags} />

      <Card>
        <CardHeader>
          <CardTitle>Reasoning</CardTitle>
        </CardHeader>
        <CardContent className="text-[13px] leading-6 text-[var(--color-text-dim)]">
          {d.reasoning_cn}
          {d.violated_rules?.length > 0 && (
            <ul className="mt-3 space-y-1.5 border-l border-[var(--color-border)] pl-3">
              {d.violated_rules.map((r, i) => (
                <li key={i} className="text-[12px] text-[var(--color-danger)]">
                  • {r}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pipeline Trace</CardTitle>
        </CardHeader>
        <CardContent>
          <PipelineDiagram trace={report.trace ?? []} />
        </CardContent>
      </Card>

      {(report.orchestrator.memory_rationale?.length ?? 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Memory Adjustments</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-[12px] text-[var(--color-text-dim)]">
              {report.orchestrator.memory_rationale.map((m, i) => (
                <li key={i}>• {m}</li>
              ))}
            </ul>
            <div className="mt-3 text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
              effective_threshold = {report.orchestrator.effective_threshold}
            </div>
          </CardContent>
        </Card>
      )}

      {!compact && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Fast Screen</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-[12px]">
              {report.fast_screen ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-[var(--color-text-muted)]">max_confidence</span>
                    <span className="font-mono">{report.fast_screen.max_confidence?.toFixed(1)}%</span>
                  </div>
                  <div className="space-y-1">
                    {(report.fast_screen.labels ?? []).slice(0, 5).map((l, i) => (
                      <div key={i} className="flex items-center justify-between text-[var(--color-text-dim)]">
                        <span>{l.Name}</span>
                        <span className="font-mono text-[11px]">{l.Confidence?.toFixed(1)}%</span>
                      </div>
                    ))}
                    {(report.fast_screen.labels ?? []).length === 0 && (
                      <span className="text-[var(--color-text-muted)]">no labels</span>
                    )}
                  </div>
                </>
              ) : (
                <span className="text-[var(--color-text-muted)]">not invoked</span>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Deep Review (Nova)</CardTitle>
            </CardHeader>
            <CardContent className="text-[12px]">
              {report.deep_review ? (
                <>
                  <div className="mb-1.5">
                    <Badge tone={report.deep_review.verdict === "allow" ? "ok" : report.deep_review.verdict === "deny" ? "danger" : "warn"}>
                      {report.deep_review.verdict}
                    </Badge>
                  </div>
                  <p className="text-[var(--color-text-dim)]">{report.deep_review.reasoning_cn}</p>
                  {report.deep_review.risk_tags?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {report.deep_review.risk_tags.map((t, i) => (
                        <Badge key={i} tone="warn" className="text-[10px]">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <span className="text-[var(--color-text-muted)]">not triggered</span>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Text Guard</CardTitle>
            </CardHeader>
            <CardContent className="text-[12px]">
              {report.text_guard ? (
                <>
                  <Badge tone={report.text_guard.action === "NONE" ? "ok" : "warn"}>{report.text_guard.action}</Badge>
                  {(report.text_guard.blocked_topics ?? []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {report.text_guard.blocked_topics!.map((t, i) => (
                        <Badge key={i} tone="danger" className="text-[10px]">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <span className="text-[var(--color-text-muted)]">not triggered</span>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <div className="text-[11px] text-[var(--color-text-muted)]">
        case <span className="font-mono">{report.case_id}</span> ·{" "}
        <span className="font-mono break-all">{report.content_s3_uri}</span>
      </div>
    </div>
  );
}
