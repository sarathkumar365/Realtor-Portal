import type { ReactNode } from "react";

export interface TimelineItem {
  id: string;
  when: string;
  title: ReactNode;
  detail?: ReactNode;
}

/** A vertical list of what happened, oldest first. */
export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="flex flex-col gap-3 border-l-2 border-rule pl-4">
      {items.map((item) => (
        <li key={item.id} className="relative">
          <span className="absolute top-1.5 -left-[21px] size-2 rounded-full bg-primary" aria-hidden />
          <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <span className="font-semibold">{item.title}</span>
            <span className="text-xs text-muted">{item.when}</span>
          </div>
          {item.detail && <div className="text-sm text-muted">{item.detail}</div>}
        </li>
      ))}
    </ol>
  );
}
