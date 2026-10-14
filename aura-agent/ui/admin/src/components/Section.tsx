import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A part of a screen under a hairline: a title, then a count or an action on the right. */
export function Section({ title, aside, children, className }: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section aria-label={title} className={cn("flex flex-col gap-3 border-t border-line-2 pt-4", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <h2>{title}</h2>
        {aside && <div className="label-caps">{aside}</div>}
      </div>
      {children}
    </section>
  );
}
