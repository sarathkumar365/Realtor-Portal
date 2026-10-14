import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import type { JobSummary } from "@/api/jobs";
import { ErrorState } from "@/components/ErrorState";
import { Reading, Readings } from "@/components/Readings";
import { Section } from "@/components/Section";
import { StatusMark } from "@/components/StatusMark";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatDay, formatMonth, greeting } from "@/lib/format";

import { useChatSummary, useJobCounts, useNeedsReview } from "./hooks/useSummary";

// The list on Home is a glance; the whole queue is on the Unbranding page.
const NEEDS_YOU_SHOWN = 5;

export function HomePage() {
  const now = new Date();
  const month = formatMonth(now);
  const counts = useJobCounts();
  const chat = useChatSummary();
  const needsReview = useNeedsReview();

  return (
    <div className="flex animate-[rise_0.5s_var(--ease-spring)_both] flex-col gap-[34px]">
      <header className="flex flex-col gap-3 pt-2">
        <span className="label-caps">{formatDay(now)}</span>
        <h1 className="text-[34px]">{greeting(now)}</h1>
      </header>

      {counts.isError ? (
        <ErrorState error={counts.error} onRetry={() => counts.refetch()} />
      ) : (
        <Readings>
          <Reading label="To review" value={counts.data?.to_review ?? "–"} marked={!!counts.data?.to_review}
            unit="cleaned and waiting for you" />
          <Reading label="Working" value={counts.data?.working ?? "–"} unit="being unbranded or filed" />
          <Reading label={`Pages cleaned · ${month}`} value={counts.data?.pages_cleaned_since ?? "–"}
            unit={counts.data ? `across ${counts.data.jobs_since} ${counts.data.jobs_since === 1 ? "job" : "jobs"}` : undefined} />
          <Reading label={`Jobs · ${month}`} value={counts.data?.jobs_since ?? "–"} unit="uploaded this month" />
        </Readings>
      )}

      <Section title="Needs you" aside={
        <Link to="/jobs" className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground">
          All jobs <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      }>
        <NeedsYou query={needsReview} waiting={counts.data?.to_review} />
      </Section>

      <Section title="Capabilities">
        <div className="grid grid-cols-3 gap-px border border-line-2 bg-line-2 max-[1000px]:grid-cols-1">
          <Capability name="Chat" state={<StatusMark kind="live">Live</StatusMark>}
            about="Realtors ask about projects and get answers from the brokerage's own records.">
            {chat.isError ? (
              <span role="alert" className="flex items-center gap-2 text-[13px] text-fg-2">
                Could not load usage.
                <Button variant="bare" size="sm" onClick={() => chat.refetch()}>Try again</Button>
              </span>
            ) : (
              <Figure value={chat.data?.active_users} label={`people · ${chat.data?.days ?? 30} days`} />
            )}
          </Capability>
          <Capability to="/jobs" name="Unbranding" about="Removes builder branding from PDFs, adds ours, and files them in Drive once you approve."
            state={counts.data?.to_review
              ? <StatusMark kind="review">{counts.data.to_review} to review</StatusMark>
              : <StatusMark kind="done">Up to date</StatusMark>}>
            <Figure value={counts.data?.jobs_since} label={`jobs · ${month}`} />
            <Figure value={counts.data?.working} label="working" />
          </Capability>
          <Capability name="Next capability" planned state={<span className="label-caps">Planned</span>}
            about="New tasks appear here as the agent learns them." />
        </div>
      </Section>
    </div>
  );
}

/** `waiting` is the true count; the list itself stops at the server's page size. */
function NeedsYou({ query, waiting }: { query: ReturnType<typeof useNeedsReview>; waiting: number | undefined }) {
  if (query.isPending) return <Skeleton className="h-24" />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (query.data.length === 0) return <p className="py-2 text-fg-3">Nothing is waiting for you.</p>;
  const shown = query.data.slice(0, NEEDS_YOU_SHOWN);
  const more = Math.max(waiting ?? query.data.length, query.data.length) - shown.length;
  return (
    <ul className="flex flex-col">
      {shown.map((job) => <NeedsYouRow key={job.id} job={job} />)}
      {more > 0 && (
        <li className="border-t border-line-2 px-1 pt-3">
          <Link to="/jobs" className="label-caps transition-colors hover:text-foreground">
            {more} more
          </Link>
        </li>
      )}
    </ul>
  );
}

function NeedsYouRow({ job }: { job: JobSummary }) {
  return (
    <li className="border-t border-line-2 first:border-t-0">
      <Link to={`/jobs/${job.id}`}
        className="grid grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_auto] items-center gap-4 px-1 py-[13px]
          transition-colors duration-200 hover:bg-raise max-[820px]:grid-cols-[minmax(0,1fr)_auto]">
        <span className="min-w-0">
          <span className="block truncate text-[14px] tracking-[-0.01em]">{job.project}</span>
          <span className="block truncate text-[13px] text-fg-3">{job.builder} · {job.city}</span>
        </span>
        <span className="label-caps truncate max-[820px]:hidden">{formatDateTime(job.created_at)}</span>
        <StatusMark kind="review">Needs review</StatusMark>
      </Link>
    </li>
  );
}

function Capability({ name, state, about, to, planned = false, children }: {
  name: string;
  state: ReactNode;
  about: string;
  to?: string;
  planned?: boolean;
  children?: ReactNode;
}) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <span className={planned ? "text-[15px] text-fg-3" : "text-[15px] tracking-[-0.015em]"}>{name}</span>
        {state}
      </div>
      <p className={planned ? "m-0 max-w-[44ch] text-[14px] text-fg-3" : "m-0 max-w-[44ch] text-[14px] text-fg-2"}>{about}</p>
      {children && <div className="mt-auto flex gap-[30px]">{children}</div>}
    </>
  );
  const box = "flex flex-col gap-3.5 bg-background p-[18px] text-left";
  return to ? (
    <Link to={to} className={`${box} transition-colors duration-200 hover:bg-raise`}>{body}</Link>
  ) : (
    <div className={box}>{body}</div>
  );
}

function Figure({ value, label }: { value: number | undefined; label: string }) {
  return (
    <div>
      <div className="reading text-[24px]">{value ?? "–"}</div>
      <span className="label-caps">{label}</span>
    </div>
  );
}
