import { ExternalLink } from "lucide-react";

import { download } from "@/api/download";
import { type JobDocument, type JobEvent, outputPdfPath } from "@/api/jobs";
import { DownloadButton } from "@/components/DownloadButton";
import { KeyValueList } from "@/components/KeyValueList";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";

import { DOC_TYPE, DOCUMENT_STATUS, hasOutput, pairPages, removals, wholeFileFindings } from "../model";
import { FindingList } from "./FindingList";
import { PagePair } from "./PagePair";
import { RemovedItems } from "./RemovedItems";

/** Everything about one document: its result, what was removed, and every page
 * before and after. */
export function DocumentReview({ jobId, document, events }: {
  jobId: string;
  document: JobDocument;
  events: JobEvent[];
}) {
  const status = DOCUMENT_STATUS[document.status];
  const cleaned = hasOutput(document);
  const failedBecause = document.status === "FAILED"
    ? events.findLast((event) => event.document_id === document.id && event.result === "failed")?.detail?.reason
    : null;
  const fileFindings = wholeFileFindings(document);

  return (
    <Card className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">
            {document.doc_type ? DOC_TYPE[document.doc_type] : `Document ${document.position}`}
          </h2>
          <p className="text-sm text-muted">Uploaded as {document.filename}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={status.tone}>{status.label}</Badge>
          {document.drive_file_id && (
            <a className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
              href={`https://drive.google.com/file/d/${encodeURIComponent(document.drive_file_id)}/view`}
              target="_blank" rel="noreferrer">
              Open in Drive<ExternalLink className="size-3" aria-hidden />
            </a>
          )}
          {cleaned && (
            <DownloadButton label="Download cleaned PDF"
              onDownload={() => download(outputPdfPath(jobId, document.position), `document-${document.position}.pdf`)} />
          )}
        </div>
      </header>

      {failedBecause != null && (
        <p role="alert" className="rounded-lg bg-danger/10 p-3 text-sm text-danger">
          Could not be unbranded: {String(failedBecause)}
        </p>
      )}
      {document.status === "BLOCKED" && (
        <p className="rounded-lg bg-danger/10 p-3 text-sm text-danger">
          Blocked by a check below. It will not be filed; review it and download it if it is usable.
        </p>
      )}

      <KeyValueList items={[
        { label: "Pages", value: `${document.page_count} → ${document.page_count - (document.dropped_pages?.length ?? 0)}` },
        { label: "Rounds", value: document.rounds ?? "—" },
        { label: "Cost", value: formatMoney(document.cost_usd) },
        { label: "Findings", value: document.findings?.length ?? 0 },
      ]} />

      {cleaned && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold">Removed</h3>
            <RemovedItems items={removals(document)} />
          </div>
          {fileFindings.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-semibold">About the whole file</h3>
              <FindingList findings={fileFindings} />
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col gap-4">
        <h3 className="text-sm font-semibold">Pages</h3>
        {pairPages(document).map((pairing) => (
          <PagePair key={pairing.source} jobId={jobId} position={document.position} pairing={pairing} showOutput={cleaned} />
        ))}
      </div>
    </Card>
  );
}
