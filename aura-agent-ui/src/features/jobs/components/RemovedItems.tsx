import type { Outcome } from "@/api/jobs";

import { describeRemoval } from "../model";

export function RemovedItems({ items }: { items: Outcome[] }) {
  if (items.length === 0) return <p className="text-sm text-muted">Nothing removed.</p>;
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {items.map((item, index) => (
        <li key={index}>
          <span className="font-semibold">{describeRemoval(item)}</span>
          <span className="text-muted"> — {item.action.why}</span>
        </li>
      ))}
    </ul>
  );
}
