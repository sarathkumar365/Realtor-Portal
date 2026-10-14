import { ArrowRight, ExternalLink } from "lucide-react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { download } from "@/api/download";
import { ApiError } from "@/api/errors";
import { type Job, type JobDocument, type JobEvent, outputPdfPath, pageImage } from "@/api/jobs";
import { AuthImage } from "@/components/AuthImage";
import { DownloadButton } from "@/components/DownloadButton";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Reading, Readings } from "@/components/Readings";
import { Section } from "@/components/Section";
import { StatusMark } from "@/components/StatusMark";
import { Timeline } from "@/components/Timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime, formatMoney, formatTime } from "@/lib/format";

import { ReviewViewer } from "./components/ReviewViewer";
import { useFileJob, useJob } from "./hooks/useJobs";
import {
  changeCount, DOCUMENT_STATUS, documentName, firstKeptPage, hasOutput, isStale, JOB_STATUS, keptPages, passedCount,
} from "./model";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  const viewer = useViewerState();

  if (job.isPending) return <LoadingState label="Loading the job" />;
  if (job.isError) return <ErrorState error={job.error} onRetry={() => job.refetch()} title="Could not load this job" />;

  const data = job.data;
  const status = JOB_STATUS[data.status];
  const documents = data.documents ?? [];
  const cleaned = documents.filter(hasOutput);
  const pages = documents.reduce((sum, document) => sum + document.page_count, 0);
  const kept = documents.reduce((sum, document) => sum + keptPages(document), 0);
  const changes = documents.reduce((sum, document) => sum + changeCount(document), 0);
  const ended = !["RECEIVED", "UNBRANDING"].includes(data.status);

  return (
    <div className="flex flex-col gap-[34px]">
      <PageHeader
        trail={[{ label: "Unbranding", to: "/jobs" }]}
        title={data.project}
        description={`${data.builder} · ${data.city}, ${data.province} · uploaded ${formatDateTime(data.created_at)} by ${data.uploader}`}
        actions={<>
          {data.drive_folder_id && (
            <Button variant="bare" asChild>
              <a href={`https://drive.google.com/drive/folders/${encodeURIComponent(data.drive_folder_id)}`}
                target="_blank" rel="noreferrer">Drive folder<ExternalLink aria-hidden /></a>
            </Button>
          )}
          {cleaned.length > 0 && (
            <DownloadButton size="md" label={cleaned.length > 1 ? "Download all" : "Download"}
              onDownload={() => downloadAll(data.id, cleaned)} />
          )}
          {data.status === "UNBRANDED" && <FileInDrive job={data} />}
        </>}
      />

      {(data.error || data.instructions || data.dry_run || isStale(data.status, data.created_at)) && (
        <div className="-mt-4 flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            {data.dry_run && <Badge title="Filed in the Drive Test folder">Test run</Badge>}
            {isStale(data.status, data.created_at) && <Badge tone="warning">Open for more than a day</Badge>}
          </div>
          {data.error && <p role="alert" className="border-l-2 border-danger pl-3 text-danger">{data.error}</p>}
          {data.instructions && (
            <p className="border-l-2 border-line pl-3 text-fg-2">
              <span className="label-caps mr-2">Instructions</span>{data.instructions}
            </p>
          )}
        </div>
      )}

      <Readings>
        <Reading label="Status"><StatusMark kind={status.kind}>{status.label}</StatusMark></Reading>
        <Reading label="Documents" value={documents.length} unit={`${pages} pages${kept !== pages ? `, ${kept} kept` : ""}`} />
        <Reading label="Changes" value={changes} marked={data.status === "UNBRANDED" && changes > 0} unit="branding items removed" />
        <Reading label="Final check" value={ended ? `${passedCount(documents)}/${documents.length}` : "–"}
          unit={ended ? "documents passed" : "runs after unbranding"} />
      </Readings>

      <Section title="Documents" aside={cleaned.length > 0 ? "Open one to compare" : undefined}>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(290px,1fr))] gap-3.5">
          {documents.map((document) => (
            <DocumentCard key={document.id} jobId={data.id} document={document} events={data.events} />
          ))}
        </div>
      </Section>

      <RunDetails job={data} />

      {viewer.open && (
        <ReviewViewer job={data} position={viewer.position} page={viewer.page}
          onPage={viewer.turn} onDocument={(position) => {
            const document = documents.find((candidate) => candidate.position === position);
            viewer.turn(document ? firstKeptPage(document) : 1, position);
          }}
          onClose={viewer.close} />
      )}
    </div>
  );
}

/** Every cleaned document, one after another: browsers refuse a burst of saves
 * started at once. One that fails does not stop the rest; the error names it. */
async function downloadAll(jobId: string, documents: JobDocument[]) {
  const failed: string[] = [];
  let reason = "";
  for (const document of documents) {
    try {
      await download(outputPdfPath(jobId, document.position), `document-${document.position}.pdf`);
    } catch (error) {
      failed.push(documentName(document));
      reason ||= error instanceof ApiError ? error.message : "try again";
    }
  }
  if (failed.length > 0) {
    throw new ApiError("server", `${failed.join(", ")} not saved (${reason})`);
  }
}

/**
 * Which document and page the viewer shows, kept in the URL (`?doc=2&page=5`) so a
 * page can be linked to. Opening pushes one history entry and turning pages
 * replaces it, so Back closes the viewer rather than walking back through pages.
 */
function useViewerState() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const doc = Number(params.get("doc"));
  const page = Number(params.get("page")) || 1;
  const pushed = (location.state as { viewer?: boolean } | null)?.viewer === true;
  return {
    open: Number.isInteger(doc) && doc > 0,
    position: doc,
    page,
    turn: (next: number, position = doc) =>
      navigate({ search: `?doc=${position}&page=${next}` }, { replace: true, state: { viewer: pushed } }),
    close: () => (pushed ? navigate(-1) : navigate({ search: "" }, { replace: true })),
  };
}

function DocumentCard({ jobId, document, events }: { jobId: string; document: JobDocument; events: JobEvent[] }) {
  const status = DOCUMENT_STATUS[document.status];
  const failedBecause = document.status === "FAILED"
    ? events.findLast((event) => event.document_id === document.id && event.result === "failed")?.detail?.reason
    : null;
  const page = firstKeptPage(document);
  const cleaned = hasOutput(document);
  const image = (version: "source" | "output") => (
    <AuthImage compact alt={`${documentName(document)}, page ${page} ${version === "source" ? "as uploaded" : "after unbranding"}`}
      className="paper-dim aspect-[8.5/11] overflow-hidden rounded-[2px] bg-white group-hover:opacity-100"
      queryKey={["page", jobId, document.position, page, version]}
      load={(signal) => pageImage(jobId, document.position, page, version, signal)} />
  );
  return (
    <div className="flex flex-col overflow-hidden rounded-[10px] border border-line-2 bg-raise transition-colors duration-300 hover:border-line">
      <Link to={{ search: `?doc=${document.position}&page=${page}` }} state={{ viewer: true }}
        aria-label={`${documentName(document)}: compare before and after`} className="group flex flex-col">
        <div className="grid grid-cols-2 gap-3 border-b border-line-2 px-[18px] pt-[18px] pb-4">
          <div><span className="label-caps mb-[7px] block">Before</span>{image("source")}</div>
          <div>
            <span className="label-caps mb-[7px] block">After</span>
            {cleaned ? image("output") : (
              <div className="grid aspect-[8.5/11] place-items-center rounded-[2px] border border-dashed border-line label-caps">
                Not yet
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between gap-2 px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-[15px] tracking-[-0.015em]">{documentName(document)}</div>
            <span className="label-caps">
              {document.page_count} {document.page_count === 1 ? "page" : "pages"}
              {cleaned && <> · <span className="text-gold-text">{changeCount(document)} changes</span></>}
            </span>
          </div>
          <span className="flex items-center gap-3">
            <StatusMark kind={status.kind}>{status.label}</StatusMark>
            <ArrowRight className="size-3.5 text-fg-3 transition-colors group-hover:text-foreground" aria-hidden />
          </span>
        </div>
      </Link>
      {failedBecause != null && (
        <p role="alert" className="mx-4 mb-3.5 border-l-2 border-danger pl-3 text-[12.5px] text-danger">
          Could not be unbranded: {String(failedBecause)}
        </p>
      )}
      {document.status === "BLOCKED" && (
        <p className="mx-4 mb-3.5 border-l-2 border-danger pl-3 text-[12.5px] text-danger">
          Blocked by a check. It will not be filed; open it to see why, and download it if it is usable.
        </p>
      )}
    </div>
  );
}

function RunDetails({ job }: { job: Job }) {
  const documents = job.documents ?? [];
  const cost = documents.reduce((sum, document) => sum + (document.cost_usd ?? 0), 0);
  const rounds = documents.reduce((sum, document) => sum + (document.rounds ?? 0), 0);
  return (
    <details className="group border-t border-line-2 pt-3.5">
      <summary className="label-caps cursor-pointer list-none transition-colors hover:text-fg-2 [&::-webkit-details-marker]:hidden">
        Run details <span className="group-open:hidden">+</span><span className="hidden group-open:inline">−</span>
      </summary>
      <div className="mt-3.5 flex flex-col gap-6">
        <Readings>
          <Reading label="Rounds" value={rounds} unit={`across ${documents.length} ${documents.length === 1 ? "document" : "documents"}`} />
          <Reading label="Model cost" value={formatMoney(cost)} />
          <Reading label="Time" value={duration(job.created_at, job.ended_at)} unit={job.ended_at ? "upload to end" : "still open"} />
          <Reading label="Job"><span className="font-mono text-[12px] break-all text-fg-2">{job.id}</span></Reading>
        </Readings>
        <div>
          <h3 className="label-caps mb-3">What happened</h3>
          <Timeline items={job.events.map((event, index) => ({
            id: String(index),
            when: formatTime(event.at),
            title: `${event.action}: ${event.result}`,
            detail: describeEvent(event),
          }))} />
        </div>
      </div>
    </details>
  );
}

function duration(start: string, end: string | null | undefined): string {
  if (!end) return "–";
  const seconds = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")} h`
    : `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
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
  const passed = passedCount(job.documents ?? []);
  function run() {
    file.mutate(undefined, {
      onSuccess: () => toast.success("Filing in Drive. This page updates when it is done."),
      onError: (error) => toast.error(error instanceof ApiError ? error.message : "Could not start filing."),
    });
  }
  return (
    <Button onClick={run} disabled={file.isPending || passed === 0}
      title={`Files the ${passed} ${passed === 1 ? "document" : "documents"} that passed in a private Drive folder${job.dry_run ? " (the Test folder)" : ""}`}>
      {file.isPending ? "Starting" : "File in Drive"}
    </Button>
  );
}
