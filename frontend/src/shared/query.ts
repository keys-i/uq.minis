/** Own remote snapshots while editor stores retain unsaved work */
import { QueryClient } from "@tanstack/react-query";

export const queries = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 120_000,
      retry: false,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});
