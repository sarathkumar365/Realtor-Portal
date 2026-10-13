import type { ReactNode } from "react";

/** Labelled facts in a grid: a summary block. */
export function KeyValueList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-6 gap-y-3">
      {items.map(({ label, value }) => (
        <div key={label}>
          <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
          <dd className="mt-0.5 text-sm font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
