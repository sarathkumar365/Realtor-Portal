import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getOrganization, type Organization, saveOrganization } from "@/api/organization";

const KEY = ["organization"] as const;

export function useOrganization() {
  return useQuery({ queryKey: KEY, queryFn: ({ signal }) => getOrganization(signal), staleTime: Infinity });
}

export function useSaveOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveOrganization,
    onSuccess: (saved: Organization) => queryClient.setQueryData(KEY, saved),
  });
}
