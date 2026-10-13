import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full rounded-lg border-[1.5px] border-border bg-surface px-3 py-2 text-sm text-foreground",
        "placeholder:text-placeholder disabled:opacity-50 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
