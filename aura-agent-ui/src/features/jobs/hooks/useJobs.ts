import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ENDED, fileJob, getJob, getLimits, type JobStatus, listJobs } from "@/api/jobs";

export const jobKeys = {
  all: ["jobs"] as const,
  list: (status: JobStatus | null) => ["jobs", "list", status] as const,
  one: (jobId: string) => ["jobs", "one", jobId] as const,
};

const POLL_MS = 5_000;
const POLL_AFTER_ERROR_MS = 30_000;

export function useJobs(status: JobStatus | null) {
  return useQuery({
    queryKey: jobKeys.list(status),
    queryFn: ({ signal }) => listJobs(status, signal),
    refetchInterval: (query) => (query.state.status === "error" ? POLL_AFTER_ERROR_MS : 15_000),
  });
}

/** Polls while the job is open, stops when it ends; TanStack pauses it in a
 * background tab. After a failed poll it waits longer before the next. */
export function useJob(jobId: string) {
  return useQuery({
    queryKey: jobKeys.one(jobId),
    queryFn: ({ signal }) => getJob(jobId, signal),
    refetchInterval: (query) => {
      if (query.state.status === "error") return POLL_AFTER_ERROR_MS;
      const job = query.state.data;
      return job && ENDED.has(job.status) ? false : POLL_MS;
    },
  });
}

/** Sends an unbranded job to filing; the job query then polls again until filed. */
export function useFileJob(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => fileJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: jobKeys.all }),
  });
}

/** The server's upload limits; they change only with its configuration. */
export function useUploadLimits() {
  return useQuery({ queryKey: ["upload-limits"], queryFn: ({ signal }) => getLimits(signal), staleTime: Infinity });
}
