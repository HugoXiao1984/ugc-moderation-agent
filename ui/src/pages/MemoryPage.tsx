import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { JurisdictionPicker } from "@/components/JurisdictionPicker";
import { Uploader } from "@/components/Uploader";
import { SamplePicker } from "@/components/SamplePicker";
import { ReportView } from "@/components/ReportView";
import { markMisjudgment, moderate, moderateReplay, recentMemory } from "@/lib/api";
import type { Jurisdiction, MemoryRecord, ModerationReport } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

export function MemoryPage() {
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("CN");
  const [s3Uri, setS3Uri] = useState("");
  const [report, setReport] = useState<ModerationReport | null>(null);
  const [hasCached, setHasCached] = useState(false);     // true after first full run
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [markMsg, setMarkMsg] = useState<string | null>(null);
  const [lastElapsed, setLastElapsed] = useState<number | null>(null);
  const [lastMode, setLastMode] = useState<"full" | "replay" | null>(null);

  const refresh = async () => {
    try {
      const r = await recentMemory(25);
      setRecords(r.records);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  // Reset cache if a new image is uploaded
  useEffect(() => {
    setHasCached(false);
    setReport(null);
    setMarkMsg(null);
    setLastElapsed(null);
    setLastMode(null);
  }, [s3Uri]);

  const run = async () => {
    if (!s3Uri) return;
    setBusy(true);
    const t0 = Date.now();
    try {
      const rep = await moderate(s3Uri, jurisdiction);
      setReport(rep);
      setHasCached(true);
      setLastElapsed(Date.now() - t0);
      setLastMode("full");
    } finally {
      setBusy(false);
    }
  };

  // Re-run after marking misjudgment — reuses cached fast_screen/Nova/text_guard
  // and only re-executes Memory recall + decision. ~8s vs ~25s for a full run.
  const replay = async () => {
    if (!report) return;
    setBusy(true);
    const t0 = Date.now();
    try {
      const rep = await moderateReplay(report);
      setReport(rep);
      setLastElapsed(Date.now() - t0);
      setLastMode("replay");
    } finally {
      setBusy(false);
    }
  };

  const markAllowed = async () => {
    if (!report) return;
    const res = await markMisjudgment({
      case_id: report.case_id,
      jurisdiction: report.jurisdiction,
      original_decision: report.decision.decision,
      corrected_decision: "allow",
      summary: report.decision.reasoning_cn.slice(0, 160),
    });
    setMarkMsg(
      res.ok
        ? "✓ Memory updated — click 'Re-run (replay)' to see threshold adjustment"
        : `✗ ${res.reason}`
    );
    refresh();
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Misjudgment → learn → readjust</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <JurisdictionPicker value={jurisdiction} onChange={setJurisdiction} />
            <Uploader onUploaded={(uri) => setS3Uri(uri)} keyPrefix="mem" />
            <SamplePicker kind="image" selectedUri={s3Uri} onPick={setS3Uri} />
            <div className="flex flex-wrap gap-2">
              <Button onClick={run} disabled={!s3Uri || busy} size="md">
                {busy && lastMode !== "replay" ? "Running…" : "1. Run moderation"}
              </Button>
              <Button onClick={markAllowed} disabled={!report || busy} size="md" variant="secondary">
                2. Mark as misjudgment (→ allow)
              </Button>
              <Button
                onClick={replay}
                disabled={!hasCached || busy}
                size="md"
                variant="secondary"
                title="Re-run using cached Rekognition/Nova signals; only Memory recall + decision stage re-execute"
              >
                {busy && lastMode === "replay" ? "Replaying…" : "3. Re-run (replay, ~8s)"}
              </Button>
            </div>
            {lastElapsed != null && (
              <div className="text-[11px] text-[var(--color-text-muted)]">
                Last run: <span className="font-mono text-[var(--color-text-dim)]">{(lastElapsed / 1000).toFixed(1)}s</span>{" "}
                <span className="ml-1 uppercase tracking-wider">
                  {lastMode === "replay" ? "(replay — cached signals)" : "(full pipeline)"}
                </span>
              </div>
            )}
            {markMsg && <div className="text-xs text-[var(--color-accent)]">{markMsg}</div>}
          </CardContent>
        </Card>

        {report && <ReportView report={report} compact />}
      </div>

      <Card className="lg:sticky lg:top-4 lg:h-fit">
        <CardHeader>
          <CardTitle>AgentCore Memory · recent misjudgments</CardTitle>
          <Button size="sm" variant="ghost" onClick={refresh}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
            {records.length === 0 && <span className="text-xs text-[var(--color-text-muted)]">No records yet.</span>}
            {records.map((r) => (
              <div key={r.memory_id} className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] p-2.5 text-[11px] text-[var(--color-text-dim)]">
                <div className="mb-1 flex items-center justify-between">
                  <Badge tone="neutral" className="font-mono text-[10px]">
                    {r.memory_id.slice(0, 12)}
                  </Badge>
                  <span className="text-[10px] text-[var(--color-text-muted)]">{r.created_at}</span>
                </div>
                <div className="line-clamp-3">{r.content.split("<!--metadata:")[0]}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
