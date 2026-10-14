import { request } from "./client";
import type { components } from "./schema";

export type JobCounts = components["schemas"]["JobCounts"];
export type ChatSummary = components["schemas"]["ChatSummary"];

/** What waits and runs now, and jobs and cleaned pages since `since` (an ISO time). */
export function getJobCounts(since: string, signal?: AbortSignal): Promise<JobCounts> {
  return request<JobCounts>(`/admin/unbrander/summary?since=${encodeURIComponent(since)}`, { signal });
}

export function getChatSummary(signal?: AbortSignal): Promise<ChatSummary> {
  return request<ChatSummary>("/admin/chat/summary", { signal });
}
