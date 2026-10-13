import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-lg border-[1.5px] border-border bg-surface px-3 text-sm text-foreground",
        "placeholder:text-placeholder disabled:opacity-50",
        "aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
