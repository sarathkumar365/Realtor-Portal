import { Plus } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { type JobDocument, type JobListing, type JobStatus, type JobSummary, pageImage } from "@/api/jobs";
import { AuthImage } from "@/components/AuthImage";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusMark } from "@/components/StatusMark";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress as Meter } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";

import { useJobs } from "./hooks/useJobs";
import { changeCount, changesByPage, isStale, JOB_STATUS, progress } from "./model";

const THUMBS = 6;
// Asked for apart, so each section is capped on its own: a job waiting for review
// is never pushed out by 50 newer finished ones.
const REVIEW: JobStatus[] = ["UNBRANDED"];
const WORKING: JobStatus[] = ["RECEIVED", "UNBRANDING", "FILING"];
const DONE: JobStatus[] = ["FILED_PRIVATE", "FAILED"];
const WORKING_POLL_MS = 5_000;

export function JobListPage() {
  const review = useJobs(REVIEW, { documents: true });
  const working = useJobs(WORKING, { documents: true, pollMs: WORKING_POLL_MS });
  const done = useJobs(DONE);
  const sections = [review, working, done];
  const failed = sections.find((section) => section.isError);
  const empty = sections.every((section) => section.data?.jobs.length === 0);

  return (
    <>
      <PageHeader eyebrow="Capabilities" title="Unbranding"
        description="Builder PDFs in, brokerage-branded PDFs out."
        actions={<Button asChild><Link to="/jobs/new"><Plus aria-hidden />New job</Link></Button>} />
      {failed ? (
        <ErrorState error={failed.error} onRetry={() => sections.forEach((section) => void section.refetch())}
          title="Could not load the jobs" />
      ) : sections.some((section) => section.isPending) ? (
        <LoadingState label="Loading jobs" />
      ) : empty ? (
        <EmptyState title="No jobs yet"
          description="A job is one project's builder PDFs, cleaned of the builder's branding and marked as ours."
          action={<Button asChild><Link to="/jobs/new">Upload PDFs</Link></Button>} />
      ) : (
        <div className="flex flex-col gap-[34px]">
          <Listed listing={review.data} title="Needs your review" layout="cards">
            {(job, documents) => <ReviewCard key={job.id} job={job} documents={documents} />}
          </Listed>
          <Listed listing={working.data} title="Working" layout="stack">
            {(job, documents) => <WorkingCard key={job.id} job={job} documents={documents} />}
          </Listed>
          <Listed listing={done.data} title="Done" layout="rows">
            {(job) => <DoneRow key={job.id} job={job} />}
          </Listed>
        </div>
      )}
    </>
  );
}

/** A section of the page, left out when it has no jobs. */
const LAYOUT = {
  cards: "grid grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-3.5",
  stack: "flex flex-col gap-3",
  rows: "flex flex-col",
};

function Listed({ listing, title, layout, children }: {
  listing: JobListing | undefined;
  title: string;
  layout: keyof typeof LAYOUT;
  children: (job: JobSummary, documents: JobDocument[]) => ReactNode;
}) {
  if (!listing || listing.jobs.length === 0) return null;
  const items = listing.jobs.map((job) => children(job, listing.documents[job.id] ?? []));
  return (
    <Section title={title} aside={listing.jobs.length}>
      {layout === "rows" ? <ul className={LAYOUT.rows}>{items}</ul> : <div className={LAYOUT[layout]}>{items}</div>}
    </Section>
  );
}

function Notes({ job }: { job: JobSummary }) {
  return (
    <>
      {isStale(job.status, job.created_at) && (
        <Badge tone="warning" title="Open for more than a day: is the worker running?">Stuck?</Badge>
      )}
      {job.dry_run && <Badge title="Filed in the Drive Test folder">Test</Badge>}
    </>
  );
}

const card = "flex flex-col rounded-[10px] border border-line-2 bg-raise text-left transition-colors duration-300 hover:border-line";

function ReviewCard({ job, documents }: { job: JobSummary; documents: JobDocument[] }) {
  const pages = documents.reduce((sum, document) => sum + document.page_count, 0);
  const changes = documents.reduce((sum, document) => sum + changeCount(document), 0);
  const thumbs = documents.flatMap((document) => {
    const counts = changesByPage(document);
    return Array.from({ length: document.page_count }, (_, index) => ({
      document, page: index + 1, changes: counts.get(index + 1) ?? 0,
    }));
  }).slice(0, THUMBS);

  return (
    <Link to={`/jobs/${job.id}`} className={`${card} group`}>
      <div className="flex gap-1.5 px-4 pt-4" aria-hidden>
        {documents.length > 0
          ? thumbs.map(({ document, page, changes: onPage }) => (
            <div key={`${document.position}-${page}`}
              className="paper-dim relative aspect-[8.5/11] max-w-[52px] flex-1 overflow-hidden rounded-[2px] bg-white group-hover:opacity-100">
              <AuthImage compact alt={`Page ${page}`} className="absolute inset-0"
                queryKey={["page", job.id, document.position, page, "source"]}
                load={(signal) => pageImage(job.id, document.position, page, "source", signal)} />
              {onPage > 0 && (
                <span className="absolute top-[3px] right-[3px] z-10 min-w-[15px] rounded-[2px] bg-gold px-[3px] text-center font-mono text-[9px] leading-[15px] text-[#09090b]">
                  {onPage}
                </span>
              )}
            </div>
          ))
          : Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="aspect-[8.5/11] max-w-[52px] flex-1" />)}
      </div>
      <div className="flex flex-col gap-2 px-4 pt-3.5 pb-4">
        <div className="flex items-start justify-between gap-3">
          <span className="text-[15px] tracking-[-0.015em]">{job.project}</span>
          <StatusMark kind="review">{JOB_STATUS[job.status].label}</StatusMark>
        </div>
        <span className="text-[12.5px] text-fg-2">{job.builder} · {job.city}</span>
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-caps">
            {documents.length > 0
              ? <>{documents.length} {documents.length === 1 ? "doc" : "docs"} · {pages} pages · <span className="text-gold-text">{changes} changes</span></>
              : formatDateTime(job.created_at)}
          </span>
          <Notes job={job} />
        </div>
      </div>
    </Link>
  );
}

function WorkingCard({ job, documents }: { job: JobSummary; documents: JobDocument[] }) {
  const status = JOB_STATUS[job.status];
  const now = progress({ status: job.status, documents });
  const steps = ["Received", "Unbranding", ...(job.file_when_done || job.status === "FILING" ? ["Filing"] : [])];
  const at = steps.indexOf(now.stage === "Waiting" ? "Received" : now.stage);
  const percent = now.total ? Math.round((now.done / now.total) * 100) : 0;
  return (
    <Link to={`/jobs/${job.id}`} className={`${card} gap-3.5 p-4`}>
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="text-[15px] tracking-[-0.015em]">{job.project}</span>
          <span className="text-fg-3"> · {job.builder}</span>
        </span>
        <span className="flex items-center gap-2"><Notes job={job} /><StatusMark kind={status.kind}>{status.label}</StatusMark></span>
      </div>
      <ol className="flex flex-wrap gap-[18px]">
        {steps.map((step, index) => (
          <li key={step} className={`label-caps ${index < at ? "!text-fg-2" : index === at ? "!text-foreground" : ""}`}>
            {step}{index === at && now.current ? ` · ${now.current}` : ""}
          </li>
        ))}
      </ol>
      <Meter value={percent} label={`${job.project}: ${now.done} of ${now.total} documents done`} />
    </Link>
  );
}

function DoneRow({ job }: { job: JobSummary }) {
  const status = JOB_STATUS[job.status];
  return (
    <li className="border-t border-line-2 first:border-t-0">
      <Link to={`/jobs/${job.id}`}
        className="grid grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_auto_auto] items-center gap-4 px-1 py-[13px]
          transition-colors duration-200 hover:bg-raise max-[820px]:grid-cols-[minmax(0,1fr)_auto]">
        <span className="min-w-0">
          <span className="block truncate text-[14px] tracking-[-0.01em]">{job.project}</span>
          <span className="block truncate text-[12px] text-fg-3">{job.builder} · {job.city}</span>
        </span>
        <span className="flex items-center gap-2 max-[820px]:hidden"><Notes job={job} /></span>
        <StatusMark kind={status.kind}>{status.label}</StatusMark>
        <span className="label-caps text-right max-[820px]:hidden">{formatDateTime(job.ended_at ?? job.created_at)}</span>
      </Link>
    </li>
  );
}
