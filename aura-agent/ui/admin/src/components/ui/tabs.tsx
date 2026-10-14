import { Tabs as TabsPrimitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex gap-0.5", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("rounded-[4px] px-2.5 py-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-fg-3",
        "transition-colors duration-200 hover:text-fg-2",
        "data-[state=active]:bg-foreground data-[state=active]:text-background", className)}
      {...props}
    />
  );
}

export const TabsContent = TabsPrimitive.Content;
