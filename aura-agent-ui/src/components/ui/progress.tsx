import { Progress as ProgressPrimitive } from "radix-ui";

import { cn } from "@/lib/cn";

/** A 2px meter. `value` from 0 to 100. */
export function Progress({ value, label, className }: { value: number; label: string; className?: string }) {
  return (
    <ProgressPrimitive.Root value={value} aria-label={label}
      className={cn("relative h-0.5 w-full overflow-hidden bg-line-2", className)}>
      <ProgressPrimitive.Indicator className="h-full bg-foreground transition-transform duration-700 ease-spring"
        style={{ transform: `translateX(-${100 - value}%)` }} />
    </ProgressPrimitive.Root>
  );
}
