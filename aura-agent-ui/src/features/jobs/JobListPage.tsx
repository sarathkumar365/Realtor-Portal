import { AlertTriangle, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { JobStatus } from "@/api/jobs";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";

import { useJobs } from "./hooks/useJobs";
import { isStale, JOB_STATUS } from "./model";

const FILTERS: { value: JobStatus | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "RECEIVED", label: "Waiting" },
  { value: "UNBRANDING", label: "Unbranding" },
  { value: "UNBRANDED", label: "Ready" },
  { value: "FILED_PRIVATE", label: "Filed" },
  { value: "FAILED", label: "Failed" },
];

export function JobListPage() {
  const [filter, setFilter] = useState<JobStatus | "ALL">("ALL");
  const jobs = useJobs(filter === "ALL" ? null : filter);

  return (
    <>
      <PageHeader
        title="Unbrander jobs"
        description="Upload a project's PDFs and review what the agent did."
        actions={<Button asChild><Link to="/jobs/new"><Plus aria-hidden />New job</Link></Button>}
      />
      <Tabs value={filter} onValueChange={(value) => setFilter(value as JobStatus | "ALL")} className="mb-4">
        <TabsList aria-label="Filter by status">
          {FILTERS.map(({ value, label }) => <TabsTrigger key={value} value={value}>{label}</TabsTrigger>)}
        </TabsList>
      </Tabs>
      {jobs.isPending ? (
        <LoadingState label="Loading jobs" />
      ) : jobs.isError ? (
        <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} title="Could not load the jobs" />
      ) : jobs.data.length === 0 ? (
        <EmptyState
          title={filter === "ALL" ? "No jobs yet" : "No jobs with this status"}
          description="A job is one project's builder PDFs, unbranded and filed privately in Drive."
          action={filter === "ALL" && <Button asChild><Link to="/jobs/new">Upload PDFs</Link></Button>}
        />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeader>Project</TableHeader>
              <TableHeader>City</TableHeader>
              <TableHeader>Status</TableHeader>
              <TableHeader>Uploaded</TableHeader>
              <TableHeader>By</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.data.map((job) => (
              // The whole row opens the job: the link stretches over the row, so it stays
              // one real link (keyboard, middle-click, screen readers) rather than a
              // click handler on a <tr>.
              <TableRow key={job.id} className="relative cursor-pointer hover:bg-background">
                <TableCell>
                  <Link to={`/jobs/${job.id}`}
                    className="font-semibold text-primary after:absolute after:inset-0 hover:underline">
                    {job.project}
                  </Link>
                  <div className="text-xs text-muted">{job.builder}</div>
                </TableCell>
                <TableCell>{job.city}</TableCell>
                <TableCell>
                  {/* Above the row's link, so the badges keep their tooltips. */}
                  <div className="relative z-10 flex w-fit flex-wrap gap-1">
                    <Badge tone={JOB_STATUS[job.status].tone}>{JOB_STATUS[job.status].label}</Badge>
                    {isStale(job.status, job.created_at) && (
                      <Badge tone="warning" title="Open for more than a day: is the worker running?">
                        <AlertTriangle className="size-3" aria-hidden />Stuck?
                      </Badge>
                    )}
                    {job.dry_run && <Badge>Test</Badge>}
                  </div>
                </TableCell>
                <TableCell>{formatDateTime(job.created_at)}</TableCell>
                <TableCell>{job.uploader}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
