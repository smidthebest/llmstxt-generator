import { useQuery } from "@tanstack/react-query";
import { listSitesOverview, SiteOverview } from "../api/client";

const ACTIVE_STATUSES = new Set(["pending", "running", "generating"]);

export function useSitesOverview() {
  return useQuery<SiteOverview[]>({
    queryKey: ["sitesOverview"],
    queryFn: listSitesOverview,
    refetchInterval: (query) => {
      const rows = query.state.data ?? [];
      const hasActiveCrawl = rows.some((row) =>
        row.latest_crawl_status ? ACTIVE_STATUSES.has(row.latest_crawl_status) : false
      );
      return hasActiveCrawl ? 1500 : 6000;
    },
  });
}
