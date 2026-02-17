import { useQuery } from "@tanstack/react-query";
import { listSites } from "../api/client";

export function useSites() {
  return useQuery({
    queryKey: ["sites"],
    queryFn: listSites,
  });
}
