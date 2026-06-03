import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { uploadImage } from "@/lib/api";

// Default to redacted previews so NSFW samples aren't displayed in the open
// during live demos. Set VITE_DEMO_REDACT_THUMBNAILS=false for dev screens
// where the image is not sensitive.
const REDACT_DEFAULT =
  (import.meta.env?.VITE_DEMO_REDACT_THUMBNAILS ?? "true") !== "false";

export function Uploader({
  onUploaded,
  accept = "image/*",
  disabled = false,
  keyPrefix = "up",
}: {
  onUploaded: (s3_uri: string, preview: string, filename: string) => void;
  accept?: string;
  disabled?: boolean;
  keyPrefix?: string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [sizeBytes, setSizeBytes] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (f: File) => {
    setBusy(true);
    setError(null);
    setRevealed(false);       // always re-redact on new upload
    setFilename(f.name);
    setSizeBytes(f.size);
    try {
      const url = URL.createObjectURL(f);
      setPreview(url);
      const r = await uploadImage(f);
      onUploaded(r.s3_uri, url, f.name);
    } catch (e: any) {
      setError(String(e).slice(0, 200));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div
        className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-panel-2)] p-6 text-center transition hover:border-[var(--color-accent)] hover:bg-[color-mix(in_oklab,var(--color-accent)_6%,transparent)]"
        onClick={() => !disabled && fileRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
        }}
        onDrop={async (e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) await handleFile(f);
        }}
      >
        {preview ? (
          REDACT_DEFAULT && !revealed ? (
            // Redacted state: no image rendered, just a neutral card with
            // the filename + a "reveal" affordance. Nothing leaks on screen.
            <div
              className="flex max-h-56 w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-8"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                Preview redacted
              </div>
              <div className="font-mono text-[11px] text-[var(--color-text-dim)] line-clamp-1">
                {filename ?? "uploaded"}
                {sizeBytes != null && ` · ${(sizeBytes / 1024).toFixed(0)} KB`}
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
            <div
              className="group relative cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                if (REDACT_DEFAULT) setRevealed(false);
              }}
              title={REDACT_DEFAULT ? "Click to hide" : undefined}
            >
              <img
                src={preview}
                alt="preview"
                className="max-h-56 max-w-full rounded-md"
              />
              {REDACT_DEFAULT && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-md bg-[var(--color-panel)]/0 text-[11px] uppercase tracking-wider text-transparent transition group-hover:bg-[var(--color-panel)]/50 group-hover:text-[var(--color-text)]">
                  Click to hide
                </div>
              )}
            </div>
          )
        ) : (
          <>
            <div className="text-sm text-[var(--color-text-dim)]">拖拽图片到此处，或点击上传</div>
            <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">JPG / PNG · 上传到 S3 后触发审核</div>
          </>
        )}
      </div>
      <Input
        ref={fileRef}
        id={`${keyPrefix}-file`}
        type="file"
        accept={accept}
        className="hidden"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f) await handleFile(f);
        }}
      />
      {busy && <div className="text-xs text-[var(--color-accent)]">Uploading…</div>}
      {error && <div className="text-xs text-[var(--color-danger)]">{error}</div>}
      {preview && !busy && (
        <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
          换一张
        </Button>
      )}
    </div>
  );
}
