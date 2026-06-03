import { useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Badge } from "@/components/ui/Badge";
import { fetchMeta } from "@/lib/api";
import { SinglePage } from "@/pages/SinglePage";
import { JurisdictionPage } from "@/pages/JurisdictionPage";
import { MemoryPage } from "@/pages/MemoryPage";
import { BatchPage } from "@/pages/BatchPage";
import { VideoPage } from "@/pages/VideoPage";
import type { MetaInfo } from "@/lib/types";

export default function App() {
  const [meta, setMeta] = useState<MetaInfo | null>(null);

  useEffect(() => {
    fetchMeta().then(setMeta).catch(() => setMeta(null));
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="bg-grid">
        <header className="border-b border-[var(--color-border)]">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="size-8 rounded-md bg-[color-mix(in_oklab,var(--color-accent)_25%,transparent)] ring-1 ring-[color-mix(in_oklab,var(--color-accent)_50%,transparent)]" />
              <div>
                <h1 className="text-sm font-semibold tracking-tight text-[var(--color-text)]">UGC Moderation Agent</h1>
                <p className="text-[11px] text-[var(--color-text-muted)]">Strands Agents × Amazon Bedrock AgentCore</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {meta && (
                <Badge tone="neutral" className="font-mono text-[10px]">{meta.aws_region}</Badge>
              )}
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-6 py-6">
          <Tabs defaultValue="single">
            <TabsList>
              <TabsTrigger value="single">① Single image</TabsTrigger>
              <TabsTrigger value="multi">② Jurisdictions</TabsTrigger>
              <TabsTrigger value="memory">③ Memory loop</TabsTrigger>
              <TabsTrigger value="batch">④ Batch</TabsTrigger>
              <TabsTrigger value="video">⑤ Video</TabsTrigger>
            </TabsList>
            <TabsContent value="single"><SinglePage /></TabsContent>
            <TabsContent value="multi"><JurisdictionPage /></TabsContent>
            <TabsContent value="memory"><MemoryPage /></TabsContent>
            <TabsContent value="batch"><BatchPage /></TabsContent>
            <TabsContent value="video"><VideoPage /></TabsContent>
          </Tabs>
        </main>

        <footer className="mx-auto max-w-7xl px-6 pb-10 pt-4 text-[10px] text-[var(--color-text-muted)]">
          {meta ? (
            <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono">
              <span>Memory: {meta.memory_id ?? "—"}</span>
              <span>Guardrail: {meta.guardrail_id ?? "—"}</span>
              <span>Code Interpreter: {meta.code_interpreter_id ?? "default"}</span>
              <span>Client mode: {meta.client_mode}</span>
            </div>
          ) : (
            <span>Backend unavailable. Start it via `uv run uvicorn backend.api:app --reload --port 8000`.</span>
          )}
        </footer>
      </div>
    </div>
  );
}

