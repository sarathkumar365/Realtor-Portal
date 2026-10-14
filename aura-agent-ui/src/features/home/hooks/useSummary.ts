import { useQuery } from "@tanstack/react-query";

import { listJobs } from "@/api/jobs";
import { getChatSummary, getJobCounts } from "@/api/summary";
import { startOfMonth } from "@/lib/format";

const POLL_MS = 15_000;
const POLL_AFTER_ERROR_MS = 30_000;
const poll = (query: { state: { status: string } }) =>
  query.state.status === "error" ? POLL_AFTER_ERROR_MS : POLL_MS;

/** Jobs waiting and running, and this month's jobs and pages. The sidebar's
 * review count reads the same query. */
export function useJobCounts() {
  const since = startOfMonth(new Date());
  return useQuery({
    queryKey: ["summary", "jobs", since],
    queryFn: ({ signal }) => getJobCounts(since, signal),
    refetchInterval: poll,
  });
}

export function useChatSummary() {
  return useQuery({ queryKey: ["summary", "chat"], queryFn: ({ signal }) => getChatSummary(signal) });
}

/** The jobs cleaned and waiting for an admin, newest first. */
export function useNeedsReview() {
  return useQuery({
    queryKey: ["summary", "needs-review"],
    queryFn: async ({ signal }) => (await listJobs(["UNBRANDED"], {}, signal)).jobs,
    refetchInterval: poll,
  });
}
