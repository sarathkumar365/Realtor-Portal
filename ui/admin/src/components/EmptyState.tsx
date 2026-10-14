import type { ReactNode } from "react";

/** Nothing to show yet, and what to do about it. */
export function EmptyState({ title, description, action }: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-[10px] border border-dashed border-line px-6 py-10 text-center">
      <p className="font-semibold">{title}</p>
      {description && <p className="max-w-md text-[14px] text-fg-3">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
