import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";
import { forwardRef } from "react";

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "inline-flex h-10 items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-1 text-sm",
      className
    )}
    {...props}
  />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex h-8 items-center justify-center whitespace-nowrap rounded-md px-4 text-[13px] font-medium",
      "text-[var(--color-text-dim)] transition data-[state=active]:bg-[var(--color-panel-2)] data-[state=active]:text-[var(--color-text)]",
      "data-[state=active]:shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
      className
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    forceMount
    className={cn(
      "mt-6 focus-visible:outline-none data-[state=inactive]:hidden",
      className
    )}
    {...props}
  />
));
TabsContent.displayName = "TabsContent";
