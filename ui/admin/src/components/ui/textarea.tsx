import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full rounded-[4px] border border-line bg-raise px-3 py-2 text-foreground",
        "transition-colors duration-200 placeholder:text-fg-3 hover:border-fg-3 focus:border-foreground focus:outline-none",
        "disabled:opacity-40 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
