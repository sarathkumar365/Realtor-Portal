import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div aria-hidden className={cn("animate-pulse rounded-[4px] bg-raise-2", className)} {...props} />;
}
