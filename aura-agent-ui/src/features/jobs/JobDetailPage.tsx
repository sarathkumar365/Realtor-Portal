import { ArrowLeft, ExternalLink, FolderUp } from "lucide-react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import type { Job, JobEvent } from "@/api/jobs";
import { ErrorState } from "@/components/ErrorState";
import { KeyValueList } from "@/components/KeyValueList";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Timeline } from "@/components/Timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatDateTime, formatMoney, formatTime } from "@/lib/format";

import { DocumentReview } from "./components/DocumentReview";
import { useFileJob, useJob } from "./hooks/useJobs";
import { isStale, JOB_STATUS } from "./model";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);

  if (job.isPending) return <LoadingState label="Loading the job" />;
  if (job.isError) return <ErrorState error={job.error} onRetry={() => job.refetch()} title="Could not load this job" />;

  const data = job.data;
  const status = JOB_STATUS[data.status];
  const documents = data.documents ?? [];
  const cost = documents.reduce((sum, document) => sum + (document.cost_usd ?? 0), 0);

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-3">
        <Link to="/jobs"><ArrowLeft aria-hidden />All jobs</Link>
      </Button>
      <PageHeader
        title={`${data.project} — ${data.builder}`}
        description={`${data.city}, ${data.province}`}
        actions={data.drive_folder_id && (
          <Button variant="secondary" asChild>
            <a href={`https://drive.google.com/drive/folders/${encodeURIComponent(data.drive_folder_id)}`}
              target="_blank" rel="noreferrer">
              Drive folder<ExternalLink aria-hidden />
            </a>
          </Button>
        )}
      />
      <div className="flex flex-col gap-6">
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Badge tone={status.tone}>{status.label}</Badge>
            {data.dry_run && <Badge title="Filed in the Drive Test folder">Test run</Badge>}
            {isStale(data.status, data.created_at) && <Badge tone="warning">Open for more than a day</Badge>}
          </div>
          {data.error && <p role="alert" className="rounded-lg bg-danger/10 p-3 text-sm text-danger">{data.error}</p>}
          <KeyValueList items={[
            { label: "Uploaded", value: formatDateTime(data.created_at) },
            { label: "By", value: data.uploader },
            { label: "Ended", value: formatDateTime(data.ended_at) },
            { label: "Documents", value: documents.length },
            { label: "Cost", value: formatMoney(cost) },
          ]} />
          {data.instructions && (
            <p className="text-sm"><span className="font-semibold">Instructions: </span>{data.instructions}</p>
          )}
          {data.status === "UNBRANDED" && <FileInDrive job={data} />}
        </Card>

        {documents.map((document) => (
          <DocumentReview key={document.id} jobId={data.id} document={document} events={data.events} />
        ))}

        <Card>
          <h2 className="mb-4 text-lg font-bold">What happened</h2>
          <Timeline items={data.events.map((event, index) => ({
            id: String(index),
            when: formatTime(event.at),
            title: `${event.action}: ${event.result}`,
            detail: describeEvent(event),
          }))} />
        </Card>
      </div>
    </>
  );
}

function describeEvent(event: JobEvent): string {
  const detail = event.detail ?? {};
  const parts = [event.actor === "agent" ? "Agent" : event.actor];
  if (typeof detail.reason === "string") parts.push(detail.reason);
  if (typeof detail.name === "string") parts.push(detail.name);
  if (Array.isArray(detail.files)) parts.push(detail.files.join(", "));
  if (typeof detail.cost_usd === "number") parts.push(formatMoney(detail.cost_usd));
  return parts.join(" · ");
}

/** Filing is a choice: an unbranded job can stay a download. Blocked documents are
 * never filed; the server uploads only those that passed. */
function FileInDrive({ job }: { job: Job }) {
  const file = useFileJob(job.id);
  const passed = (job.documents ?? []).filter((document) => document.status === "VERIFIED").length;
  function run() {
    file.mutate(undefined, {
      onSuccess: () => toast.success("Filing in Drive. This page updates when it is done."),
      onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not start filing."),
    });
  }
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-success/10 p-3">
      <p className="text-sm">
        Unbranded. Download the cleaned PDFs below, or file the {passed} that passed in a private
        Drive folder{job.dry_run ? " (the Test folder)" : ""}.
      </p>
      <Button onClick={run} disabled={file.isPending}>
        <FolderUp aria-hidden />{file.isPending ? "Starting" : "File in Drive"}
      </Button>
    </div>
  );
}
