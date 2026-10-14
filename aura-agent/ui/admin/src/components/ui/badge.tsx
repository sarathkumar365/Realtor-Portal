import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

// Outlined and monochrome: a job's state is shown by StatusMark, so a badge only
// carries side notes such as "Test" or "Open for more than a day".
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border border-line px-2 py-px text-[10.5px] whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "text-fg-2",
        info: "text-fg-2",
        success: "text-fg-2",
        warning: "text-foreground",
        danger: "border-danger/40 text-danger",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({ className, tone, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
