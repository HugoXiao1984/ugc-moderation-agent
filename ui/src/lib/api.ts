import type {
  ModerationReport,
  Jurisdiction,
  MetaInfo,
  TraceResult,
  MemoryRecord,
  Sample,
  VideoModerationReport,
  VideoLimits,
  VideoProgress,
} from "./types";

const BASE = ""; // use Vite proxy: /api → localhost:8000

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${txt.slice(0, 200)}`);
  }
  return resp.json() as Promise<T>;
}

export async function fetchMeta(): Promise<MetaInfo> {
  return jsonOrThrow<MetaInfo>(await fetch(`${BASE}/api/meta`));
}

export async function uploadImage(file: File): Promise<{ s3_uri: string; size_bytes: number }> {
  const fd = new FormData();
  fd.append("file", file);
  return jsonOrThrow(await fetch(`${BASE}/api/upload`, { method: "POST", body: fd }));
}

export async function moderate(
  content_s3_uri: string,
  jurisdiction: Jurisdiction,
  ocr_text = ""
): Promise<ModerationReport> {
  return jsonOrThrow<ModerationReport>(
    await fetch(`${BASE}/api/moderate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_s3_uri, jurisdiction, ocr_text }),
    })
  );
}

export async function moderateReplay(
  previousReport: ModerationReport
): Promise<ModerationReport> {
  return jsonOrThrow<ModerationReport>(
    await fetch(`${BASE}/api/moderate/replay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ previous_report: previousReport }),
    })
  );
}

export async function moderateMulti(
  content_s3_uri: string,
  jurisdictions: Jurisdiction[] = ["CN", "EU", "US"],
  ocr_text = ""
): Promise<{ results: Record<Jurisdiction, ModerationReport> }> {
  return jsonOrThrow(
    await fetch(`${BASE}/api/moderate/multi`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_s3_uri, jurisdictions, ocr_text }),
    })
  );
}

export async function batchModerate(
  content_s3_uris: string[],
  jurisdiction: Jurisdiction = "CN"
): Promise<{ elapsed_s: number; reports: ModerationReport[] }> {
  return jsonOrThrow(
    await fetch(`${BASE}/api/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_s3_uris, jurisdiction }),
    })
  );
}

export async function markMisjudgment(body: {
  case_id: string;
  jurisdiction: Jurisdiction;
  original_decision: string;
  corrected_decision: string;
  summary: string;
}): Promise<{ ok: boolean; reason?: string }> {
  return jsonOrThrow<{ ok: boolean; reason?: string }>(
    await fetch(`${BASE}/api/misjudgment`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

export async function recentMemory(limit = 20): Promise<{ records: MemoryRecord[] }> {
  return jsonOrThrow(await fetch(`${BASE}/api/memory/recent?limit=${limit}`));
}

export async function fetchSamples(): Promise<{ samples: Sample[] }> {
  return jsonOrThrow(await fetch(`${BASE}/api/samples`));
}

export async function latestTrace(caseId?: string): Promise<TraceResult> {
  const q = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
  return jsonOrThrow<TraceResult>(await fetch(`${BASE}/api/trace/latest${q}`));
}

export async function moderateVideo(
  content_s3_uri: string,
  jurisdiction: Jurisdiction = "CN",
  case_id?: string,
): Promise<VideoModerationReport> {
  return jsonOrThrow<VideoModerationReport>(
    await fetch(`${BASE}/api/video/moderate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_s3_uri, jurisdiction, case_id }),
    })
  );
}

export async function videoProgress(case_id: string): Promise<VideoProgress | null> {
  const resp = await fetch(`${BASE}/api/video/progress/${encodeURIComponent(case_id)}`);
  if (resp.status === 404) return null;
  return jsonOrThrow<VideoProgress>(resp);
}

export async function videoLimits(): Promise<VideoLimits> {
  return jsonOrThrow<VideoLimits>(await fetch(`${BASE}/api/video/limits`));
}
