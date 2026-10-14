import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** Cells divided by 1px of the hairline colour: the gap shows the background. */
export function Readings({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-px border border-line-2 bg-line-2", className)}>
      {children}
    </dl>
  );
}

/**
 * One cell: a label, a value and an optional unit line. A number goes in as
 * `value` and is set as a reading; anything else (a StatusMark, a name) goes in
 * as `children` and keeps its own look. `marked` turns the reading gold, for a
 * count of changes waiting to be checked.
 */
export function Reading({ label, value, unit, marked = false, children }: {
  label: string;
  value?: ReactNode;
  unit?: ReactNode;
  marked?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5 bg-background px-[18px] py-4">
      <dt className="label-caps">{label}</dt>
      <dd className="m-0 flex min-w-0 flex-col gap-1.5">
        {value !== undefined && (
          <span className={cn("reading text-[clamp(22px,2.4vw,30px)]", marked && "text-gold-text")}>{value}</span>
        )}
        {children}
        {unit && <span className="text-[12.5px] text-fg-2">{unit}</span>}
      </dd>
    </div>
  );
}
