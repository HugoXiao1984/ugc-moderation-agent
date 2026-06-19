import { useEffect, useState } from "react";
import { fetchSamples } from "@/lib/api";
import type { Sample } from "@/lib/types";
import { cn } from "@/lib/utils";

// One-click demo samples that already live in S3, so a live demo never waits on
// (or fails at) uploading over a flaky venue network. Picking one just hands the
// existing s3_uri to the parent — identical to what a fresh upload produces, so
// all downstream moderation logic is unchanged.
export function SamplePicker({
  kind,
  selectedUri,
  onPick,
  className,
}: {
  kind: "image" | "video";
  selectedUri?: string;
  onPick: (s3_uri: string) => void;
  className?: string;
}) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchSamples()
      .then((r) => setSamples(r.samples.filter((s) => s.kind === kind)))
      .catch(() => setError(true));
  }, [kind]);

  if (error || samples.length === 0) return null;

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
        示例素材（点击直接使用，免上传）
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {samples.map((s) => {
          const active = selectedUri === s.s3_uri;
          return (
            <button
              key={s.s3_uri}
              onClick={() => onPick(s.s3_uri)}
              title={s.scenario}
              className={cn(
                "rounded-md border px-2 py-1.5 text-center text-[12px] font-medium transition",
                active
                  ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_12%,transparent)] text-[var(--color-text)]"
                  : "border-[var(--color-border)] bg-[var(--color-panel-2)] text-[var(--color-text)] hover:border-[var(--color-border-strong)]"
              )}
            >
              {s.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
