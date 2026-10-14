import { QueryClient } from "@tanstack/react-query";

import { isRetryable } from "@/api/errors";

/** Reads retry twice when trying again could help (offline, timeout, 5xx), never
 * on a 4xx. Writes never retry on their own: a repeated upload is a second job. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failures, error) => failures < 2 && isRetryable(error),
        staleTime: 10_000,
      },
      mutations: { retry: false },
    },
  });
}
