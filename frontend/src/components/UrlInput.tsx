import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSite, CrawlConfig } from "../api/client";
import CrawlConfigPanel from "./CrawlConfigPanel";

export default function UrlInput() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [crawlConfig, setCrawlConfig] = useState<CrawlConfig>({});
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (u: string) => createSite(u, crawlConfig),
    onSuccess: (site) => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      navigate(`/sites/${site.id}`);
    },
    onError: () => setError("Failed to submit URL. Please check the format."),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      new URL(url);
    } catch {
      setError("Please enter a valid URL (e.g., https://example.com)");
      return;
    }
    mutation.mutate(url);
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="flex gap-2">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
          className="flex-1 px-4 py-3 bg-transparent border border-[#444] rounded-lg text-[#f0f0f0] placeholder-[#444] focus:outline-none focus:border-[#7b8ff5]/50 transition-colors font-mono text-sm"
        />
        <button
          type="submit"
          disabled={mutation.isPending}
          className="px-5 py-3 bg-[#7b8ff5] text-white rounded-lg text-sm font-medium hover:bg-[#8d9ff7] disabled:opacity-40 transition-colors whitespace-nowrap"
        >
          {mutation.isPending ? "..." : "Generate"}
        </button>
      </div>
      <div className="mt-3">
        <CrawlConfigPanel onChange={setCrawlConfig} />
      </div>
      {error && (
        <p className="mt-2 text-red-400/80 text-xs anim-enter">{error}</p>
      )}
    </form>
  );
}
