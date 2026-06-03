import { Badge, Dot } from "@/components/ui/Badge";
import type { Decision } from "@/lib/types";

const MAP: Record<Decision, { tone: "ok" | "warn" | "danger"; label: string }> = {
  allow: { tone: "ok", label: "ALLOW" },
  deny: { tone: "danger", label: "DENY" },
  human_review: { tone: "warn", label: "HUMAN REVIEW" },
};

export function DecisionBadge({ decision }: { decision: Decision }) {
  const cfg = MAP[decision] ?? MAP.human_review;
  return (
    <Badge tone={cfg.tone} className="uppercase">
      <Dot tone={cfg.tone} />
      {cfg.label}
    </Badge>
  );
}
