import type { Finding } from "@/api/jobs";
import { Badge } from "@/components/ui/badge";

import { CHECK, SEVERITY } from "../model";

export function FindingList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return null;
  return (
    <ul className="flex flex-col gap-2" aria-label="Findings">
      {findings.map((finding, index) => (
        <li key={index} className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={SEVERITY[finding.severity].tone}>{SEVERITY[finding.severity].label}</Badge>
            <span className="font-semibold">{CHECK[finding.check]}</span>
          </div>
          <p className="break-words text-muted">{finding.detail}</p>
        </li>
      ))}
    </ul>
  );
}
