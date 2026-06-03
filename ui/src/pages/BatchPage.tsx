import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { JurisdictionPicker } from "@/components/JurisdictionPicker";
import { Progress } from "@/components/ui/Progress";
import { DecisionBadge } from "@/components/DecisionBadge";
import { FlagBadge } from "@/components/FlagBadge";
import { batchModerate, uploadImage } from "@/lib/api";
import type { Jurisdiction, ModerationReport } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

export function BatchPage() {
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("CN");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [reports, setReports] = useState<ModerationReport[]>([]);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!files.length) return;
    setBusy(true);
    setUploadProgress(0);
    setReports([]);
    setElapsed(null);
    try {
      // Parallel upload — completed count drives the progress bar.
      let completed = 0;
      const uris = await Promise.all(
        files.map(async (f) => {
          const r = await uploadImage(f);
          completed += 1;
          setUploadProgress(Math.round((completed / files.length) * 100));
          return r.s3_uri;
        })
      );
      const res = await batchModerate(uris, jurisdiction);
      setReports(res.reports);
      setElapsed(res.elapsed_s);
    } finally {
      setBusy(false);
    }
  };

  const deepCount = reports.filter((r) => r.trace?.includes("deep_review")).length;
  const heavyCount = reports.filter((r) => r.trace?.includes("decision_heavy")).length;
  const avgConf = reports.length ? reports.reduce((s, r) => s + (r.decision?.confidence ?? 0), 0) / reports.length : 0;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Batch moderation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <JurisdictionPicker value={jurisdiction} onChange={setJurisdiction} />
          <input
            type="file"
            multiple
            accept="image/*"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="block w-full rounded-md border border-dashed border-[var(--color-border-strong)] bg-[var(--color-panel-2)] p-3 text-xs text-[var(--color-text-dim)] file:mr-3 file:rounded-md file:border-0 file:bg-[var(--color-accent)] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-black hover:file:brightness-110"
          />
          {files.length > 0 && (
            <div className="text-xs text-[var(--color-text-dim)]">
              {files.length} file(s) selected ·{" "}
              {files.map((f) => f.name).join(", ")}
            </div>
          )}
          <Button onClick={run} disabled={!files.length || busy} size="lg">
            {busy ? "Running…" : `▶ Moderate ${files.length} images in parallel`}
          </Button>
          {busy && uploadProgress < 100 && (
            <div className="space-y-1">
              <div className="text-[11px] text-[var(--color-text-muted)]">Uploading {uploadProgress}%</div>
              <Progress value={uploadProgress} />
            </div>
          )}
        </CardContent>
      </Card>

      {reports.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Total" value={reports.length} />
            <Stat label="Elapsed" value={`${elapsed?.toFixed(1)}s`} />
            <Stat label="Deep review triggered" value={`${deepCount}/${reports.length}`} />
            <Stat label="Avg confidence" value={`${Math.round(avgConf * 100)}%`} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Results</CardTitle>
              <div className="text-[11px] text-[var(--color-text-muted)]">
                {heavyCount} heavy · {reports.length - heavyCount} light · deep_review hit rate{" "}
                {Math.round((deepCount / reports.length) * 100)}%
              </div>
            </CardHeader>
            <CardContent>
              <div className="divide-y divide-[var(--color-border)]">
                <div className="grid grid-cols-[100px_130px_1fr_80px_100px_1fr] items-center gap-3 pb-2 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <span>Decision</span>
                  <span>Flag</span>
                  <span>Reasoning</span>
                  <span className="text-right">Deep?</span>
                  <span className="text-right">Confidence</span>
                  <span>URI</span>
                </div>
                {reports.map((r, i) => (
                  <div key={i} className="grid grid-cols-[100px_130px_1fr_80px_100px_1fr] items-center gap-3 py-2 text-[12px]">
                    <span>
                      {"error" in r ? (
                        <Badge tone="danger">ERR</Badge>
                      ) : (
                        <DecisionBadge decision={r.decision.decision} />
                      )}
                    </span>
                    <span>
                      {"error" in r ? (
                        <span className="text-[var(--color-text-muted)]">—</span>
                      ) : (
                        <FlagBadge flag={r.decision?.flag} />
                      )}
                    </span>
                    <span className="line-clamp-1 text-[var(--color-text-dim)]">
                      {"error" in r ? (r as any).error : r.decision?.reasoning_cn}
                    </span>
                    <span className="text-right text-[var(--color-text-dim)]">
                      {r.trace?.includes("deep_review") ? "✓" : "—"}
                    </span>
                    <span className="text-right font-mono text-[var(--color-text-dim)]">
                      {r.decision ? `${Math.round(r.decision.confidence * 100)}%` : "—"}
                    </span>
                    <span className="font-mono text-[10px] text-[var(--color-text-muted)] line-clamp-1">
                      {r.content_s3_uri ?? ""}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1 text-xl font-semibold text-[var(--color-text)]">{value}</div>
    </div>
  );
}
