import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { JurisdictionPicker } from "@/components/JurisdictionPicker";
import { Uploader } from "@/components/Uploader";
import { SamplePicker } from "@/components/SamplePicker";
import { ReportView } from "@/components/ReportView";
import { TraceChart } from "@/components/TraceChart";
import { latestTrace, markMisjudgment, moderate } from "@/lib/api";
import type { Jurisdiction, ModerationReport, TraceResult } from "@/lib/types";

export function SinglePage() {
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("CN");
  const [s3Uri, setS3Uri] = useState<string>("");
  const [ocr, setOcr] = useState<string>("");
  const [report, setReport] = useState<ModerationReport | null>(null);
  const [trace, setTrace] = useState<TraceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [corrected, setCorrected] = useState<"allow" | "deny" | "human_review">("allow");
  const [markBusy, setMarkBusy] = useState(false);
  const [markMsg, setMarkMsg] = useState<string | null>(null);

  const run = async () => {
    if (!s3Uri) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const r = await moderate(s3Uri, jurisdiction, ocr);
      setReport(r);
      const t = await latestTrace(r.case_id);
      setTrace(t);
    } catch (e: any) {
      setError(String(e).slice(0, 300));
    } finally {
      setBusy(false);
    }
  };

  const handleMark = async () => {
    if (!report) return;
    setMarkBusy(true);
    setMarkMsg(null);
    try {
      const res = await markMisjudgment({
        case_id: report.case_id,
        jurisdiction: report.jurisdiction,
        original_decision: report.decision.decision,
        corrected_decision: corrected,
        summary: report.decision.reasoning_cn.slice(0, 120),
      });
      setMarkMsg(res.ok ? "✓ 已写入 Memory" : `✗ ${res.reason ?? "失败"}`);
    } catch (e: any) {
      setMarkMsg(`✗ ${e}`);
    } finally {
      setMarkBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Input</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="mb-2 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Jurisdiction
              </label>
              <JurisdictionPicker value={jurisdiction} onChange={setJurisdiction} />
            </div>

            <div>
              <label className="mb-2 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Image
              </label>
              <Uploader onUploaded={(uri) => setS3Uri(uri)} keyPrefix="single" />
              <SamplePicker kind="image" selectedUri={s3Uri} onPick={setS3Uri} className="mt-3" />
              {s3Uri && (
                <div className="mt-2 break-all font-mono text-[10px] text-[var(--color-text-muted)]">{s3Uri}</div>
              )}
            </div>

            <div>
              <label className="mb-2 block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                OCR / Caption text (optional)
              </label>
              <Input value={ocr} onChange={(e) => setOcr(e.target.value)} placeholder="e.g. 图片上的广告文字" />
            </div>

            <Button onClick={run} disabled={!s3Uri || busy} size="lg" className="w-full">
              {busy ? "Running…" : "▶ Run moderation"}
            </Button>
            {error && <div className="rounded-md border border-[var(--color-danger)] bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] p-2 text-xs text-[var(--color-danger)]">{error}</div>}
          </CardContent>
        </Card>

        {report && (
          <Card>
            <CardHeader>
              <CardTitle>Flag as misjudgment</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-[11px] text-[var(--color-text-muted)]">
                Original: <span className="font-mono text-[var(--color-text-dim)]">{report.decision.decision}</span>
              </div>
              <div className="flex gap-2">
                {(["allow", "deny", "human_review"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setCorrected(v)}
                    className={`rounded-md border px-2.5 py-1 text-[11px] ${
                      corrected === v
                        ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                        : "border-[var(--color-border)] text-[var(--color-text-dim)]"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
              <Button size="sm" variant="secondary" onClick={handleMark} disabled={markBusy} className="w-full">
                {markBusy ? "Saving…" : "Record to AgentCore Memory"}
              </Button>
              {markMsg && <div className="text-[11px] text-[var(--color-text-dim)]">{markMsg}</div>}
            </CardContent>
          </Card>
        )}
      </div>

      <div className="space-y-6">
        {report ? <ReportView report={report} /> : (
          <Card>
            <CardHeader>
              <CardTitle>Report</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-xs text-[var(--color-text-muted)]">Upload an image and click Run moderation to see the Agent output.</span>
            </CardContent>
          </Card>
        )}
        <TraceChart trace={trace} />
      </div>
    </div>
  );
}
