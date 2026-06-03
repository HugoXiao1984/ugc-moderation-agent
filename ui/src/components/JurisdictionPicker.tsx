import type { Jurisdiction } from "@/lib/types";
import { cn } from "@/lib/utils";

const OPTIONS: Array<{ key: Jurisdiction; flag: string; name: string; hint: string }> = [
  { key: "CN", flag: "🇨🇳", name: "China", hint: "Strict + red-line" },
  { key: "EU", flag: "🇪🇺", name: "EU", hint: "DSA + GDPR" },
  { key: "US", flag: "🇺🇸", name: "US", hint: "First Amdt. + COPPA" },
];

export function JurisdictionPicker({
  value,
  onChange,
  className,
}: {
  value: Jurisdiction;
  onChange: (v: Jurisdiction) => void;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-3 gap-2", className)}>
      {OPTIONS.map((o) => {
        const active = value === o.key;
        return (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            className={cn(
              "flex flex-col items-start gap-0.5 rounded-lg border p-3 text-left transition",
              active
                ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_10%,transparent)]"
                : "border-[var(--color-border)] bg-[var(--color-panel-2)] hover:border-[var(--color-border-strong)]"
            )}
          >
            <span className="text-lg leading-none">{o.flag}</span>
            <span className="text-xs font-semibold text-[var(--color-text)]">{o.name}</span>
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{o.hint}</span>
          </button>
        );
      })}
    </div>
  );
}
