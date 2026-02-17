import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  getSite,
  listCrawlJobs,
  getLlmsTxt,
  startCrawl,
} from "../api/client";
import { useCrawlStatus } from "../hooks/useCrawlStatus";
import CrawlProgress from "../components/CrawlProgress";
import LlmsTxtPreview from "../components/LlmsTxtPreview";
import LlmsTxtEditor from "../components/LlmsTxtEditor";
import ScheduleConfig from "../components/ScheduleConfig";

type Tab = "progress" | "result" | "schedule";

export default function SitePage() {
  const { id } = useParams<{ id: string }>();
  const siteId = Number(id);
  const [tab, setTab] = useState<Tab>("progress");
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId),
  });

  const { data: jobs } = useQuery({
    queryKey: ["crawlJobs", siteId],
    queryFn: () => listCrawlJobs(siteId),
    refetchInterval: 3000,
  });

  const { data: crawlJob, isLoading: crawlLoading } = useCrawlStatus(
    siteId,
    activeJobId
  );

  const { data: llmsTxt } = useQuery({
    queryKey: ["llmstxt", siteId],
    queryFn: () => getLlmsTxt(siteId),
    retry: false,
    refetchInterval: crawlJob?.status === "completed" ? false : 5000,
  });

  const recrawlMutation = useMutation({
    mutationFn: () => startCrawl(siteId),
    onSuccess: (job) => setActiveJobId(job.id),
  });

  // Pick up the latest job automatically and set initial tab
  const initialTabSet = useRef(false);
  useEffect(() => {
    if (jobs && jobs.length > 0 && activeJobId === null) {
      setActiveJobId(jobs[0].id);
      if (!initialTabSet.current) {
        initialTabSet.current = true;
        const latestStatus = jobs[0].status;
        if (latestStatus === "completed" || latestStatus === "failed") {
          setTab("result");
        }
      }
    }
  }, [jobs, activeJobId]);

  // Only auto-switch to result when a crawl *transitions* from running to completed
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (
      prevStatus.current === "running" &&
      crawlJob?.status === "completed"
    ) {
      setTab("result");
    }
    prevStatus.current = crawlJob?.status;
  }, [crawlJob?.status]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "progress", label: "Progress" },
    { key: "result", label: "Result" },
    { key: "schedule", label: "Schedule" },
  ];

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link to="/" className="text-blue-600 hover:underline text-sm">
        &larr; Back
      </Link>

      <div className="mt-4 mb-6">
        <h1 className="text-2xl font-bold">
          {site?.title || site?.domain || "Loading..."}
        </h1>
        {site?.description && (
          <p className="text-gray-600 mt-1">{site.description}</p>
        )}
        {site && (
          <p className="text-sm text-gray-400 mt-1">{site.url}</p>
        )}
      </div>

      <div className="flex gap-1 border-b mb-6">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "progress" && (
        <div className="space-y-4">
          <CrawlProgress job={crawlJob} isLoading={crawlLoading} />
          <button
            onClick={() => recrawlMutation.mutate()}
            disabled={
              recrawlMutation.isPending || crawlJob?.status === "running"
            }
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 text-sm"
          >
            Re-crawl
          </button>
        </div>
      )}

      {tab === "result" && (
        <div className="space-y-4">
          {llmsTxt ? (
            <>
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setEditing(!editing)}
                  className="px-3 py-1.5 text-sm rounded-lg border hover:bg-gray-50"
                >
                  {editing ? "Preview" : "Edit"}
                </button>
                <a
                  href={`/api/sites/${siteId}/llms-txt/download`}
                  className="px-3 py-1.5 text-sm rounded-lg border hover:bg-gray-50 inline-block"
                >
                  Download
                </a>
              </div>
              {editing ? (
                <LlmsTxtEditor
                  siteId={siteId}
                  initialContent={llmsTxt.content}
                />
              ) : (
                <LlmsTxtPreview content={llmsTxt.content} />
              )}
            </>
          ) : (
            <div className="text-gray-500">
              No generated file yet. Wait for the crawl to complete.
            </div>
          )}
        </div>
      )}

      {tab === "schedule" && <ScheduleConfig siteId={siteId} />}
    </div>
  );
}
