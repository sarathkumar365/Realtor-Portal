import { API_BASE, request, send } from "./client";
import type { components } from "./schema";

export type Job = components["schemas"]["JobDetail"];
export type JobSummary = components["schemas"]["JobSummary"];
export type JobStatus = components["schemas"]["JobStatus"];
export type JobDocument = components["schemas"]["JobDocument"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type Finding = components["schemas"]["Finding"];
export type Outcome = components["schemas"]["Outcome"];
export type JobEvent = components["schemas"]["JobEvent"];
export type JobAccepted = components["schemas"]["JobAccepted"];
export type PageVersion = "source" | "output";
export type UploadLimits = components["schemas"]["UploadLimits"];

export function getLimits(signal?: AbortSignal): Promise<UploadLimits> {
  return request<UploadLimits>("/admin/unbrander/limits", { signal });
}

/** Statuses the worker has nothing to do for: polling stops. UNBRANDED waits for
 * a person (or an agent) to ask for filing. */
export const ENDED: ReadonlySet<JobStatus> = new Set(["UNBRANDED", "FILED_PRIVATE", "FAILED"]);

export interface JobListing {
  jobs: JobSummary[];
  /** Each job's documents by job id, when asked for. */
  documents: Record<string, JobDocument[]>;
}

/** Newest first, in any of `statuses` (every status when empty); with
 * `documents`, each job's documents come in the same response. */
export async function listJobs(statuses: JobStatus[], { documents = false } = {},
                               signal?: AbortSignal): Promise<JobListing> {
  const query = new URLSearchParams(statuses.map((status) => ["status", status]));
  if (documents) query.set("documents", "true");
  const listed = await request<{ jobs: JobSummary[]; documents?: Record<string, JobDocument[]> | null }>(
    `/admin/unbrander/jobs${query.size ? `?${query}` : ""}`, { signal });
  return { jobs: listed.jobs, documents: listed.documents ?? {} };
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/admin/unbrander/jobs/${encodeURIComponent(jobId)}`, { signal });
}

function documentPath(jobId: string, position: number): string {
  return `/admin/unbrander/jobs/${encodeURIComponent(jobId)}/documents/${position}`;
}

/** One page as an image. `page` is the source page number for both versions. */
export async function pageImage(jobId: string, position: number, page: number, version: PageVersion,
                                signal?: AbortSignal): Promise<Blob> {
  const response = await send(`${documentPath(jobId, position)}/pages/${page}.jpg?version=${version}`,
    { signal, timeoutMs: 60_000 });
  return response.blob();
}

export function outputPdfPath(jobId: string, position: number): string {
  return `${documentPath(jobId, position)}/output.pdf`;
}

export const UPLOAD_URL = `${API_BASE}/admin/unbrander/jobs`;

/** File an unbranded job in Drive. 503 when Drive is not set up on the service. */
export function fileJob(jobId: string): Promise<JobAccepted> {
  return request<JobAccepted>(`/admin/unbrander/jobs/${encodeURIComponent(jobId)}/file`, { method: "POST" });
}
