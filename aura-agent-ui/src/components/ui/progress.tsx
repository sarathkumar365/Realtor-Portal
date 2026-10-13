import { Progress as ProgressPrimitive } from "radix-ui";

import { cn } from "@/lib/cn";

/** `value` from 0 to 100. */
export function Progress({ value, label, className }: { value: number; label: string; className?: string }) {
  return (
    <ProgressPrimitive.Root value={value} aria-label={label}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-rule", className)}>
      <ProgressPrimitive.Indicator className="h-full bg-primary transition-transform"
        style={{ transform: `translateX(-${100 - value}%)` }} />
    </ProgressPrimitive.Root>
  );
}
