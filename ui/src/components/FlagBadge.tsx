import { Badge } from "@/components/ui/Badge";

// flag severity convention (agreed with backend):
//   999 — 最严重违规（色情/血腥暴力/引导广告/未成年）
//   998 — 次严重（武器/毒品/恐怖/冒犯宗教）
//   997 — 特殊文化背景冒犯（宗教/种姓/政治/性话题）
//   200 — 疑似未成年 15~18 岁
//   100 — 普通违规（吸烟饮酒/诋毁/侮辱/脏话）
//     1 — 不处理（非色情性感动作等）
//     2 — 完全不可辨识
const LABEL: Record<number, string> = {
  999: "严重违规",
  998: "次严重",
  997: "文化冒犯",
  200: "疑似未成年",
  100: "普通违规",
  1: "不处理",
  2: "不可辨识",
};

function toneFor(flag: number): "ok" | "warn" | "danger" | "neutral" {
  if (flag >= 998) return "danger";
  if (flag >= 100) return "warn";
  return "ok";
}

export function FlagBadge({
  flag,
  className,
}: {
  flag: number | undefined | null;
  className?: string;
}) {
  if (flag == null) return null;
  const tone = toneFor(flag);
  const label = LABEL[flag] ?? "未分级";
  return (
    <Badge tone={tone} className={"font-mono text-[10px] uppercase " + (className ?? "")}>
      flag {flag} · {label}
    </Badge>
  );
}

export function TagChips({
  tags,
  className,
}: {
  tags: string[] | undefined | null;
  className?: string;
}) {
  if (!tags || tags.length === 0) return null;
  return (
    <div className={"flex flex-wrap gap-1 " + (className ?? "")}>
      {tags.map((t) => (
        <span
          key={t}
          className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2 py-0.5 text-[10px] text-[var(--color-text-dim)]"
        >
          {t}
        </span>
      ))}
    </div>
  );
}
