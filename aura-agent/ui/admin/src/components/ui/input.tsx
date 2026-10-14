import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-[38px] w-full rounded-[4px] border border-line bg-raise px-3 text-foreground",
        "transition-colors duration-200 placeholder:text-fg-3 hover:border-fg-3 focus:border-foreground focus:outline-none",
        "disabled:opacity-40 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
