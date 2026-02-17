import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSite,
  listCrawlJobs,
  getLlmsTxt,
  startCrawl,
  CrawlConfig,
} from "../api/client";
import { useCrawlStatus } from "../hooks/useCrawlStatus";
import CrawlVisualization from "../components/CrawlVisualization";
import CrawlConfigPanel from "../components/CrawlConfigPanel";
import LlmsTxtPreview from "../components/LlmsTxtPreview";
import LlmsTxtEditor from "../components/LlmsTxtEditor";
import ScheduleConfig from "../components/ScheduleConfig";

type Tab = "progress" | "result" | "schedule";

const TABS: { key: Tab; label: string }[] = [
  { key: "progress", label: "Progress" },
  { key: "result", label: "Result" },
  { key: "schedule", label: "Schedule" },
];

export default function SitePage() {
  const { id } = useParams<{ id: string }>();
  const siteId = Number(id);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("progress");
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [crawlConfig, setCrawlConfig] = useState<CrawlConfig>({});

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
    refetchInterval: (query) => {
      if (crawlJob?.status === "running" || crawlJob?.status === "pending")
        return 5000;
      if (
        crawlJob?.status === "completed" &&
        activeJobId &&
        query.state.data?.crawl_job_id !== activeJobId
      )
        return 3000;
      return false;
    },
  });

  const recrawlMutation = useMutation({
    mutationFn: () => startCrawl(siteId, crawlConfig),
    onSuccess: (job) => setActiveJobId(job.id),
  });

  const initialTabSet = useRef(false);
  useEffect(() => {
    if (jobs && jobs.length > 0 && activeJobId === null) {
      setActiveJobId(jobs[0].id);
      if (!initialTabSet.current) {
        initialTabSet.current = true;
        const s = jobs[0].status;
        if (s === "completed" || s === "failed") setTab("result");
      }
    }
  }, [jobs, activeJobId]);

  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (
      prevStatus.current === "running" &&
      crawlJob?.status === "completed"
    ) {
      setTab("result");
      queryClient.invalidateQueries({ queryKey: ["llmstxt", siteId] });
    }
    prevStatus.current = crawlJob?.status;
  }, [crawlJob?.status, queryClient, siteId]);

  const copyToClipboard = () => {
    if (!llmsTxt?.content) return;
    navigator.clipboard.writeText(llmsTxt.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 anim-enter">
      {/* Back */}
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-xs tracking-widest uppercase text-[#ccc] hover:text-[#f0f0f0] transition-colors mb-6"
      >
        &larr; Back
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold text-[#f0f0f0]">
            {site?.title || site?.domain || "..."}
          </h1>
          {(() => {
            const llmsDesc = llmsTxt?.content?.match(/^> (.+)$/m)?.[1];
            const desc = llmsDesc || site?.description;
            return desc ? (
              <p className="text-[#ddd] text-sm mt-2 max-w-xl">{desc}</p>
            ) : null;
          })()}
          {site && (
            <span className="inline-block text-[10px] font-mono text-[#bbb] mt-2 tracking-wider">
              {site.url}
            </span>
          )}
        </div>
        <button
          onClick={() => recrawlMutation.mutate()}
          disabled={
            recrawlMutation.isPending || crawlJob?.status === "running"
          }
          className="text-xs tracking-widest uppercase text-[#ddd] hover:text-[#f0f0f0] border border-[#444] hover:border-[#555] px-3 py-1.5 rounded-md disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
        >
          {crawlJob?.status === "running" ? "Crawling..." : "Re-crawl"}
        </button>
      </div>

      {/* Advanced Config */}
      <div className="mb-6">
        <CrawlConfigPanel onChange={setCrawlConfig} />
      </div>

      {/* Tabs */}
      <div className="flex gap-6 mb-8 border-b border-[#383838]">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`pb-2.5 text-xs tracking-widest uppercase transition-colors border-b-2 -mb-px ${
              tab === t.key
                ? "border-[#7b8ff5] text-[#f0f0f0]"
                : "border-transparent text-[#ccc] hover:text-[#f0f0f0]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content — keep progress tab mounted to preserve SSE state */}
      <div className={tab === "progress" ? "" : "hidden"}>
        <CrawlVisualization siteId={siteId} job={crawlJob} isLoading={crawlLoading} />
      </div>

      <div className={tab === "result" ? "anim-enter" : "hidden"}>
        {llmsTxt ? (
          <>
            <div className="flex items-center gap-3 mb-5">
              <button
                onClick={() => setEditing(!editing)}
                className={`text-xs tracking-widest uppercase px-3 py-1.5 rounded-md border transition-all ${
                  editing
                    ? "bg-[#f0f0f0] text-black border-[#f0f0f0]"
                    : "border-[#444] text-[#ccc] hover:text-[#f0f0f0] hover:border-[#555]"
                }`}
              >
                {editing ? "Preview" : "Edit"}
              </button>
              <button
                onClick={copyToClipboard}
                className="text-xs tracking-widest uppercase px-3 py-1.5 rounded-md border border-[#444] text-[#ccc] hover:text-[#f0f0f0] hover:border-[#555] transition-all"
              >
                {copied ? "\u2713 Copied" : "Copy"}
              </button>
              <a
                href={`/api/sites/${siteId}/llms-txt/download`}
                className="text-xs tracking-widest uppercase px-3 py-1.5 rounded-md border border-[#444] text-[#ccc] hover:text-[#f0f0f0] hover:border-[#555] transition-all"
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
        ) : crawlJob?.status === "completed" ? (
          <div className="text-center py-20">
            <div className="inline-block w-5 h-5 border-2 border-[#444] border-t-[#7b8ff5] rounded-full animate-spin mb-4" />
            <p className="text-[#ddd] text-sm">Generating with AI...</p>
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="text-[#ccc] text-sm">
              No output yet. Run a crawl first.
            </p>
          </div>
        )}
      </div>

      <div className={tab === "schedule" ? "anim-enter" : "hidden"}>
        <ScheduleConfig siteId={siteId} />
      </div>
    </div>
  );
}
