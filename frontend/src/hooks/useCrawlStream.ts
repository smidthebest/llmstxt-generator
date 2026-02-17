import { useState, useEffect, useRef } from "react";

export interface CrawlPageEvent {
  type: "page_crawled";
  url: string;
  title: string | null;
  description: string | null;
  category: string;
  relevance_score: number;
  depth: number;
}

export interface CrawlProgressEvent {
  type: "progress";
  pages_found: number;
  pages_crawled: number;
  pages_changed: number;
  pages_added?: number;
  pages_updated?: number;
  pages_removed?: number;
  pages_unchanged?: number;
  pages_skipped: number;
  max_pages: number;
  status?: string;
}

export type CrawlEvent =
  | CrawlPageEvent
  | CrawlProgressEvent
  | { type: "completed" }
  | { type: "failed"; error: string };

interface UseCrawlStreamReturn {
  pages: CrawlPageEvent[];
  progress: CrawlProgressEvent | null;
  isComplete: boolean;
  isGenerating: boolean;
  error: string | null;
}

export function useCrawlStream(
  siteId: number,
  jobId: number | null,
  enabled: boolean = true
): UseCrawlStreamReturn {
  const [pages, setPages] = useState<CrawlPageEvent[]>([]);
  const [progress, setProgress] = useState<CrawlProgressEvent | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const prevJobId = useRef<number | null>(null);

  // Only reset state when jobId actually changes to a different value
  useEffect(() => {
    if (jobId !== prevJobId.current) {
      prevJobId.current = jobId;
      setPages([]);
      setProgress(null);
      setIsComplete(false);
      setIsGenerating(false);
      setError(null);
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !enabled) return;

    // Don't reconnect if we already completed this job
    if (isComplete) return;

    const es = new EventSource(`/api/sites/${siteId}/crawl/${jobId}/stream`);
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const data: CrawlEvent = JSON.parse(event.data);
        switch (data.type) {
          case "page_crawled":
            setPages((prev) => [...prev, data]);
            break;
          case "progress":
            setProgress(data);
            if (data.status === "generating") {
              setIsGenerating(true);
            }
            break;
          case "completed":
            setIsComplete(true);
            es.close();
            break;
          case "failed":
            setError(data.error);
            es.close();
            break;
        }
      } catch {
        // ignore parse errors (heartbeats)
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [siteId, jobId, enabled, isComplete]);

  return { pages, progress, isComplete, isGenerating, error };
}
