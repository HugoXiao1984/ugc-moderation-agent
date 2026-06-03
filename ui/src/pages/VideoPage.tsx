import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { JurisdictionPicker } from "@/components/JurisdictionPicker";
import { DecisionBadge } from "@/components/DecisionBadge";
import { FlagBadge, TagChips } from "@/components/FlagBadge";
import {
  moderateVideo,
  uploadImage,
  videoLimits,
  videoProgress,
} from "@/lib/api";
import type {
  FrameResult,
  Jurisdiction,
  VideoLimits,
  VideoModerationReport,
  VideoProgress,
} from "@/lib/types";

const REDACT_DEFAULT =
  (import.meta.env?.VITE_DEMO_REDACT_THUMBNAILS ?? "true") !== "false";

export function VideoPage() {
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("CN");
  const [s3Uri, setS3Uri] = useState("");
  const [filename, setFilename] = useState<string | null>(null);
  const [sizeBytes, setSizeBytes] = useState<number | null>(null);
  const [durationS, setDurationS] = useState<number | null>(null);
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [report, setReport] = useState<VideoModerationReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limits, setLimits] = useState<VideoLimits | null>(null);
  const [progress, setProgress] = useState<VideoProgress | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    videoLimits().then(setLimits).catch(() => setLimits(null));
  }, []);

  const handleFile = async (f: File) => {
    if (!f.type.startsWith("video/")) {
      setUploadError("Only video files are supported here.");
      return;
    }
    setUploadError(null);
    setFilename(f.name);
    setSizeBytes(f.size);
    setRevealed(false);
    setS3Uri("");
    setReport(null);
    // Create a blob URL for local playback + metadata probe (keep in state so
    // the <video> can actually render it). Release the previous URL first.
    if (localUrl) URL.revokeObjectURL(localUrl);
    const blobUrl = URL.createObjectURL(f);
    setLocalUrl(blobUrl);
    try {
      const v = document.createElement("video");
      v.preload = "metadata";
      await new Promise<void>((resolve, reject) => {
        v.onloadedmetadata = () => resolve();
        v.onerror = () => reject(new Error("metadata probe failed"));
        v.src = blobUrl;
      });
      setDurationS(Number.isFinite(v.duration) ? v.duration : null);
    } catch {
      setDurationS(null);
    }

    setUploading(true);
    try {
      const r = await uploadImage(f);      // reuses /api/upload, now accepts video
      setS3Uri(r.s3_uri);
    } catch (exc: any) {
      setUploadError(String(exc).slice(0, 200));
    } finally {
      setUploading(false);
    }
  };

  const run = async () => {
    if (!s3Uri) return;
    setBusy(true);
    setError(null);
    setReport(null);
    setProgress(null);

    // Pre-generate a case_id so we can start polling progress before the
    // moderate POST resolves. Use the same scheme as the backend default:
    // "vcase-" + first 8 hex chars of a random uuid.
    const sid = (crypto.randomUUID?.() || Math.random().toString(36).slice(2)).replace(/-/g, "");
    const caseId = `vcase-${sid.slice(0, 8)}`;

    // Poll every 1.5s until report arrives or backend reports error/done
    pollRef.current = window.setInterval(async () => {
      try {
        const p = await videoProgress(caseId);
        if (p) setProgress(p);
      } catch {
        /* progress not critical — swallow */
      }
    }, 1500);

    try {
      const r = await moderateVideo(s3Uri, jurisdiction, caseId);
      setReport(r);
    } catch (exc: any) {
      setError(String(exc).slice(0, 300));
    } finally {
      if (pollRef.current != null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      setBusy(false);
    }
  };

  useEffect(() => {
    // Clean up any lingering poller on unmount
    return () => {
      if (pollRef.current != null) window.clearInterval(pollRef.current);
    };
  }, []);

  const maxSeconds = limits?.max_video_seconds ?? 30;
  const overLimit = durationS != null && durationS > maxSeconds;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>视频审核</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <JurisdictionPicker value={jurisdiction} onChange={setJurisdiction} />
          <div
            className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-panel-2)] p-6 text-center transition hover:border-[var(--color-accent)]"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={async (e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) await handleFile(f);
            }}
          >
            {filename ? (
              REDACT_DEFAULT && !revealed ? (
                <div
                  className="flex w-full flex-col items-center justify-center gap-2"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                    Preview redacted
                  </div>
                  <div className="font-mono text-[11px] text-[var(--color-text-dim)] line-clamp-1">
                    {filename}
                    {sizeBytes != null && ` · ${(sizeBytes / 1024 / 1024).toFixed(1)} MB`}
                    {durationS != null && ` · ${durationS.toFixed(1)}s`}
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => {
                      e.stopPropagation();
                      setRevealed(true);
                    }}
                  >
                    Click to reveal (sensitive)
                  </Button>
                </div>
              ) : (
                <div className="relative w-full" onClick={(e) => e.stopPropagation()}>
                  <video
                    ref={videoRef}
                    src={localUrl || undefined}
                    controls
                    muted
                    className="max-h-56 w-full rounded-md"
                  />
                  {REDACT_DEFAULT && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="absolute right-2 top-2 bg-[var(--color-panel)]/90 backdrop-blur"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRevealed(false);
                      }}
                    >
                      ● Hide
                    </Button>
                  )}
                </div>
              )
            ) : (
              <>
                <div className="text-sm text-[var(--color-text-dim)]">
                  拖拽视频到此处，或点击上传 (MP4 / MOV)
                </div>
                <div className="text-[11px] text-[var(--color-text-muted)]">
                  视频上传到 S3 后在服务端 ffmpeg 抽帧逐帧审核
                </div>
              </>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />

          {uploading && <div className="text-xs text-[var(--color-accent)]">Uploading…</div>}
          {uploadError && <div className="text-xs text-[var(--color-danger)]">{uploadError}</div>}
          {overLimit && (
            <div className="rounded-md border border-[var(--color-danger)]/60 bg-[color-mix(in_oklab,var(--color-danger)_10%,transparent)] p-2 text-[11px] text-[var(--color-danger)]">
              视频时长过长，请缩短后重试。
            </div>
          )}

          <div className="flex gap-2">
            <Button onClick={run} disabled={!s3Uri || busy || overLimit} size="lg">
              {busy ? "Moderating video…" : "▶ Moderate video"}
            </Button>
          </div>
          {error && <div className="text-xs text-[var(--color-danger)]">{error}</div>}
        </CardContent>
      </Card>

      {busy && <VideoProgressCard progress={progress} maxSeconds={maxSeconds} />}

      {report && <VideoReport report={report} />}
    </div>
  );
}

function VideoProgressCard({
  progress,
}: {
  progress: VideoProgress | null;
  maxSeconds: number;
}) {
  const frac =
    progress && progress.frames_total > 0
      ? Math.min(100, Math.round((progress.frames_done / progress.frames_total) * 100))
      : null;
  return (
    <Card>
      <CardContent className="space-y-3 py-5">
        <div className="flex items-center justify-between text-[12px]">
          <div className="flex items-center gap-2 text-[var(--color-text)]">
            <span className="inline-block size-2 animate-pulse rounded-full bg-[var(--color-accent)]" />
            <span>{progress?.stage_label ?? "启动中…"}</span>
          </div>
          <div className="font-mono text-[11px] text-[var(--color-text-muted)]">
            {progress ? `${progress.elapsed_s.toFixed(1)}s` : "0.0s"}
          </div>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-panel-2)]">
          <div
            className="h-full bg-[var(--color-accent)] transition-[width] duration-500"
            style={{
              width:
                progress?.done
                  ? "100%"
                  : frac != null
                  ? `${frac}%`
                  : progress?.stage === "downloading" || progress?.stage === "extracting"
                  ? "12%"
                  : progress?.stage === "uploading_frames"
                  ? "25%"
                  : progress?.stage === "summarizing"
                  ? "92%"
                  : "6%",
            }}
          />
        </div>
        <div className="text-[11px] text-[var(--color-text-muted)]">
          {progress?.frames_total
            ? `已审核 ${progress.frames_done}/${progress.frames_total} 帧`
            : `正在审核中，违规内容会尽快短路返回…`}
        </div>
      </CardContent>
    </Card>
  );
}

function VideoReport({ report }: { report: VideoModerationReport }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Verdict</span>
            <div className="flex items-center gap-2">
              <Badge tone="neutral" className="font-mono text-[10px]">
                {report.elapsed_s.toFixed(1)}s · {report.frames_evaluated}/{report.frames_sampled} frames
              </Badge>
              <FlagBadge flag={report.flag} />
              <DecisionBadge decision={report.verdict} />
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-[var(--color-text-dim)]">
          <div>{report.reasoning_cn}</div>
          <TagChips tags={report.tags} />
          {report.offending_frame && (
            <div className="rounded-md border border-[var(--color-danger)]/60 bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] p-2 text-[11px]">
              <strong>Short-circuit frame @ {report.offending_frame.second}s</strong> ·{" "}
              <span className="font-mono">{report.offending_frame.top_label ?? "—"}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {(report.summary_cn || report.summary_topic) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>🎬 视频理解</span>
              {report.summary_topic && (
                <Badge tone="neutral" className="text-[10px] uppercase tracking-wide">
                  {report.summary_topic}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-[var(--color-text-dim)]">
            {report.summary_cn || "—"}
          </CardContent>
        </Card>
      )}

      {report.verdict !== "allow" && <OffendingFramesCard report={report} />}
    </div>
  );
}

function OffendingFramesCard({ report }: { report: VideoModerationReport }) {
  // Prefer frames flagged as deny / short_circuit; fall back to human_review ones.
  const denies = report.frame_results.filter(
    (f) => f.decision === "deny" || f.short_circuit,
  );
  const reviews = report.frame_results.filter((f) => f.decision === "human_review");
  const flagged = denies.length ? denies : reviews;
  if (flagged.length === 0) return null;

  const tone = report.verdict === "deny" ? "danger" : "warn";
  const title =
    report.verdict === "deny"
      ? `🚫 违规帧 (${flagged.length})`
      : `⚠️ 需人审帧 (${flagged.length})`;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{title}</span>
          <Badge tone={tone} className="text-[10px] uppercase">
            {report.verdict}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
          {flagged.map((fr) => (
            <FrameCard key={fr.second} frame={fr} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function FrameCard({ frame }: { frame: FrameResult }) {
  const tone =
    frame.decision === "deny" ? "danger" : frame.decision === "human_review" ? "warn" : "ok";
  return (
    <div
      className={
        "rounded-md border p-3 text-[12px] " +
        (frame.short_circuit
          ? "border-[var(--color-danger)] bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)]"
          : "border-[var(--color-border)] bg-[var(--color-panel-2)]")
      }
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-[var(--color-text-muted)]">
          t = {frame.second}s
        </span>
        <div className="flex items-center gap-1">
          <FlagBadge flag={frame.flag} />
          <Badge tone={tone} className="text-[10px] uppercase">
            {frame.decision}
          </Badge>
        </div>
      </div>
      {frame.top_label && (
        <div className="mb-1 text-[11px] text-[var(--color-text-dim)]">
          <span className="font-mono">{frame.top_label}</span>
        </div>
      )}
      <div className="text-[11px] leading-relaxed text-[var(--color-text-dim)]">
        {frame.reasoning_cn}
      </div>
      <TagChips tags={frame.risk_tags} className="mt-2" />
      {frame.short_circuit && (
        <div className="mt-1 text-[10px] uppercase tracking-wider text-[var(--color-danger)]">
          ⚡ short-circuit
        </div>
      )}
    </div>
  );
}
