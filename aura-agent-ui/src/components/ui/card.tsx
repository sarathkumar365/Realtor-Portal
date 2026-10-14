import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-[10px] border border-line-2 bg-raise p-5", className)} {...props} />;
}
