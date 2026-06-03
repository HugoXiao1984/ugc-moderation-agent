import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-[var(--color-accent)] text-black hover:brightness-110 shadow-[0_0_0_1px_rgba(255,255,255,0.08)_inset,0_8px_24px_-8px_color-mix(in_oklab,var(--color-accent)_60%,transparent)]",
  secondary:
    "bg-[var(--color-panel-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:border-[var(--color-border-strong)]",
  ghost: "text-[var(--color-text-dim)] hover:text-[var(--color-text)] hover:bg-[var(--color-panel-2)]",
  danger: "bg-[var(--color-danger)] text-black hover:brightness-110",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-5 text-sm font-medium",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]",
        "disabled:opacity-40 disabled:pointer-events-none",
        VARIANTS[variant],
        SIZES[size],
        className
      )}
      {...props}
    />
  )
);
Button.displayName = "Button";
