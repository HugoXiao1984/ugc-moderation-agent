import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ReportView } from "@/components/ReportView";
import { Uploader } from "@/components/Uploader";
import { moderateMulti } from "@/lib/api";
import type { Jurisdiction, ModerationReport } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

const JS: Jurisdiction[] = ["CN", "EU", "US"];
const LABELS: Record<Jurisdiction, string> = { CN: "🇨🇳 China", EU: "🇪🇺 European Union", US: "🇺🇸 United States" };

type JurisdictionState =
  | { status: "idle" }
  | { status: "running"; startedAt: number }
  | { status: "done"; report: ModerationReport; elapsedMs: number }
  | { status: "error"; message: string; elapsedMs: number };

export function JurisdictionPage() {
  const [s3Uri, setS3Uri] = useState("");
  const [states, setStates] = useState<Record<Jurisdiction, JurisdictionState>>({
    CN: { status: "idle" },
    EU: { status: "idle" },
    US: { status: "idle" },
  });
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!s3Uri) return;
    setBusy(true);
    const startedAt = Date.now();
    setStates({
      CN: { status: "running", startedAt },
      EU: { status: "running", startedAt },
      US: { status: "running", startedAt },
    });

    // Hybrid backend shares Memory/Rekognition/Nova across jurisdictions
    // and only fans out the decision stage — one call, ~25s for all three
    // (instead of 60s from naive 3× gather).
    try {
      const res = await moderateMulti(s3Uri, JS);
      const elapsedMs = Date.now() - startedAt;
      setStates((prev) => {
        const next = { ...prev };
        for (const j of JS) {
          const r = (res.results as any)[j];
          if (r && !("error" in r)) {
            next[j] = { status: "done", report: r as ModerationReport, elapsedMs };
          } else {
            next[j] = {
              status: "error",
              message: (r && r.error) || "unknown error",
              elapsedMs,
            };
          }
        }
        return next;
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const elapsedMs = Date.now() - startedAt;
      setStates({
        CN: { status: "error", message, elapsedMs },
        EU: { status: "error", message, elapsedMs },
        US: { status: "error", message, elapsedMs },
      });
    }
    setBusy(false);
  };

  const doneReports = JS.map((j) => states[j].status === "done" ? (states[j] as any).report as ModerationReport : null);
  const decisions = doneReports.map((r) => r?.decision?.decision).filter(Boolean) as string[];
  const divergent = decisions.length === JS.length && new Set(decisions).size > 1;
  const doneCount = JS.filter((j) => states[j].status === "done").length;
  const errorCount = JS.filter((j) => states[j].status === "error").length;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Same image, three jurisdictions</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-[360px_1fr]">
          <Uploader onUploaded={(uri) => setS3Uri(uri)} keyPrefix="juris" />
          <div className="flex flex-col justify-center gap-3">
            <p className="text-[12px] leading-6 text-[var(--color-text-dim)]">
              Same asset runs through <span className="font-semibold text-[var(--color-text)]">CN / EU / US</span> policy scripts in parallel. Each jurisdiction streams in as soon as it completes — no more all-or-nothing waiting.
            </p>
            <Button onClick={run} disabled={!s3Uri || busy} className="w-fit">
              {busy ? `Running… ${doneCount + errorCount}/${JS.length} done` : "▶ Compare jurisdictions"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {divergent && (
        <div className="rounded-md border border-[color-mix(in_oklab,var(--color-accent)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-accent)_10%,transparent)] p-3 text-[12px]">
          <Badge tone="accent" className="mr-2">
            Divergent outcome
          </Badge>
          Decisions differ across jurisdictions — the jurisdiction-adaptive policy layer is in effect.
        </div>
      )}

      {(busy || doneCount > 0 || errorCount > 0) && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {JS.map((j) => {
            const st = states[j];
            return (
              <Card key={j}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>{LABELS[j]}</span>
                    {st.status === "running" && (
                      <Badge tone="neutral" className="text-[10px]">Running…</Badge>
                    )}
                    {st.status === "done" && (
                      <Badge tone="ok" className="text-[10px]">
                        {(st.elapsedMs / 1000).toFixed(1)}s
                      </Badge>
                    )}
                    {st.status === "error" && (
                      <Badge tone="danger" className="text-[10px]">Error</Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {st.status === "running" && (
                    <div className="flex items-center gap-2 py-8 text-[12px] text-[var(--color-text-muted)]">
                      <span className="inline-block size-2 animate-pulse rounded-full bg-[var(--color-accent)]" />
                      Running {LABELS[j]} pipeline…
                    </div>
                  )}
                  {st.status === "done" && <ReportView report={st.report} compact />}
                  {st.status === "error" && (
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {st.message.slice(0, 200)}
                    </span>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
