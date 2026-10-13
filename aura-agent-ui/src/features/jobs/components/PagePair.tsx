import { pageImage } from "@/api/jobs";
import { AuthImage } from "@/components/AuthImage";

import type { PagePairing } from "../model";
import { FindingList } from "./FindingList";

/** One source page beside the page made from it, with what was found on it. */
export function PagePair({ jobId, position, pairing, showOutput }: {
  jobId: string;
  position: number;
  pairing: PagePairing;
  showOutput: boolean;
}) {
  const { source, output, findings, droppedBecause } = pairing;
  const image = (version: "source" | "output", alt: string) => (
    <AuthImage
      queryKey={["page", jobId, position, source, version]}
      load={(signal) => pageImage(jobId, position, source, version, signal)}
      alt={alt}
    />
  );
  return (
    <section aria-label={`Page ${source}`} className="grid gap-4 border-t border-rule pt-4 lg:grid-cols-[1fr_1fr_18rem]">
      <figure>
        <figcaption className="mb-1 text-xs font-semibold text-muted">Before · page {source}</figcaption>
        {image("source", `Page ${source} as uploaded`)}
      </figure>
      <figure>
        <figcaption className="mb-1 text-xs font-semibold text-muted">
          After{output ? ` · page ${output}` : ""}
        </figcaption>
        {!showOutput ? (
          <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted">Not cleaned yet</p>
        ) : output === null ? (
          <p className="rounded-lg border border-dashed border-border bg-surface p-6 text-center text-sm">
            <span className="font-semibold">Dropped.</span>{" "}
            <span className="text-muted">{droppedBecause}</span>
          </p>
        ) : (
          image("output", `Page ${source} after unbranding`)
        )}
      </figure>
      <div>
        {findings.length > 0
          ? <FindingList findings={findings} />
          : showOutput && output !== null && <p className="text-sm text-muted">Nothing found on this page.</p>}
      </div>
    </section>
  );
}
