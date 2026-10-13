import { Tabs as TabsPrimitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex gap-1 rounded-lg bg-rule p-1", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("rounded-md px-3 py-1.5 text-sm font-semibold text-muted",
        "data-[state=active]:bg-surface data-[state=active]:text-foreground data-[state=active]:shadow-sm", className)}
      {...props}
    />
  );
}

export const TabsContent = TabsPrimitive.Content;
