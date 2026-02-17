import { useQuery } from "@tanstack/react-query";
import { getCrawlStatus, CrawlJob } from "../api/client";

export function useCrawlStatus(siteId: number, jobId: number | null) {
  return useQuery<CrawlJob>({
    queryKey: ["crawl", siteId, jobId],
    queryFn: () => getCrawlStatus(siteId, jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed") return false;
      return 2000;
    },
  });
}
