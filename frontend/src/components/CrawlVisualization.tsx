import { useState, useEffect, useRef } from "react";
import { CrawlJob } from "../api/client";
import {
  useCrawlStream,
  CrawlPageEvent,
} from "../hooks/useCrawlStream";

interface Props {
  siteId: number;
  job: CrawlJob | undefined;
  isLoading: boolean;
}

const CATEGORY_COLORS: Record<string, string> = {
  "Getting Started": "#4ade80",
  Documentation: "#7b8ff5",
  "API Reference": "#f59e0b",
  Guides: "#a78bfa",
  Examples: "#38bdf8",
  "Core Pages": "#f0f0f0",
  FAQ: "#fb923c",
  Changelog: "#94a3b8",
  About: "#6b7280",
  Blog: "#ec4899",
  Other: "#555",
};

function DepthDots({ depth }: { depth: number }) {
  return (
    <div className="flex gap-[3px] shrink-0 w-6">
      {Array.from({ length: Math.min(depth + 1, 4) }).map((_, i) => (
        <div
          key={i}
          className="w-[5px] h-[5px] rounded-full"
          style={{
            backgroundColor:
              i === depth ? "#7b8ff5" : "rgba(123,143,245,0.3)",
          }}
        />
      ))}
    </div>
  );
}

function PageRow({ page, index }: { page: CrawlPageEvent; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const color = CATEGORY_COLORS[page.category] || "#555";

  return (
    <div
      className="rounded hover:bg-[#0a0a0a] transition-colors anim-enter"
      style={{ animationDelay: `${Math.min(index * 20, 200)}ms` }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-3 py-1.5 px-2 w-full text-left"
      >
        <DepthDots depth={page.depth} />

        <div className="flex-1 min-w-0">
          <div className="text-xs text-[#ccc] truncate">
            {page.title || page.url}
          </div>
          {page.title && (
            <div className="text-[10px] text-[#444] truncate font-mono">
              {new URL(page.url).pathname}
            </div>
          )}
        </div>

        <span
          className="text-[9px] tracking-wider uppercase px-1.5 py-[1px] rounded-full whitespace-nowrap shrink-0"
          style={{
            color,
            backgroundColor: `${color}12`,
            border: `1px solid ${color}25`,
          }}
        >
          {page.category}
        </span>

        <span
          className={`text-[10px] text-[#444] transition-transform duration-150 shrink-0 ${
            expanded ? "rotate-180" : ""
          }`}
        >
          &#9662;
        </span>
      </button>

      {expanded && (
        <div className="px-2 pb-2 pl-11 anim-enter">
          <div className="border border-[#1a1a1a] rounded-md p-3 space-y-2">
            {page.description && (
              <p className="text-[11px] text-[#888] leading-relaxed">
                {page.description.length > 300
                  ? page.description.slice(0, 300) + "..."
                  : page.description}
              </p>
            )}
            <div className="flex items-center gap-4 text-[10px] text-[#555]">
              <span className="font-mono">
                depth: {page.depth}
              </span>
              <span className="font-mono">
                relevance: {Math.round(page.relevance_score * 100)}%
              </span>
              <a
                href={page.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#7b8ff5] hover:underline font-mono truncate"
                onClick={(e) => e.stopPropagation()}
              >
                {page.url.replace(/https?:\/\//, "").slice(0, 60)}
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function CrawlVisualization({
  siteId,
  job,
  isLoading,
}: Props) {
  const isActive =
    job?.status === "running" || job?.status === "pending";
  const { pages, progress, isComplete, error } = useCrawlStream(
    siteId,
    job?.id ?? null,
    isActive
  );

  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [pages.length]);

  if (isLoading || !job) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-24 rounded anim-shimmer" />
        <div className="h-1 w-full rounded-full anim-shimmer" />
        <div className="grid grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg anim-shimmer" />
          ))}
        </div>
      </div>
    );
  }

  const found = progress?.pages_found ?? job.pages_found;
  const crawled = progress?.pages_crawled ?? job.pages_crawled;
  const changed = progress?.pages_changed ?? job.pages_changed;
  const maxPages = progress?.max_pages ?? 200;
  const pct = maxPages > 0 ? Math.min(Math.round((crawled / maxPages) * 100), 100) : 0;
  const status = isComplete
    ? "completed"
    : error
      ? "failed"
      : job.status;

  return (
    <div className="space-y-6 anim-enter">
      {/* Status */}
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center gap-2 text-xs tracking-widest uppercase ${
            status === "completed"
              ? "text-[#4ade80]"
              : status === "failed"
                ? "text-red-400/80"
                : "text-[#7b8ff5]"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              status === "completed"
                ? "bg-[#4ade80]"
                : status === "failed"
                  ? "bg-red-400"
                  : status === "running"
                    ? "bg-[#7b8ff5] animate-pulse"
                    : "bg-[#555]"
            }`}
          />
          {status}
        </span>
        {status === "running" && (
          <span className="text-xs font-mono text-[#7b8ff5]">{pct}%</span>
        )}
        {status === "running" && pages.length > 0 && (
          <span className="text-[10px] text-[#444] font-mono">
            {pages[pages.length - 1].url.replace(/https?:\/\//, "").slice(0, 50)}
          </span>
        )}
      </div>

      {/* Progress bar */}
      {(status === "running" || status === "pending") && (
        <div className="w-full h-px bg-[#1a1a1a] rounded-full overflow-hidden">
          {status === "running" ? (
            <div
              className="h-full rounded-full bar-anim transition-all duration-500"
              style={{ width: `${Math.max(pct, 3)}%` }}
            />
          ) : (
            <div className="h-full w-full anim-shimmer rounded-full" />
          )}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Found", value: found },
          { label: "Crawled", value: `${crawled} / ${maxPages}` },
          { label: "Changed", value: changed },
        ].map((s) => (
          <div key={s.label} className="py-3">
            <div className="text-xl font-mono text-[#f0f0f0]">{s.value}</div>
            <div className="text-[10px] tracking-[0.15em] uppercase text-[#555] mt-1">
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Live Feed */}
      {pages.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="text-[10px] tracking-[0.2em] uppercase text-[#555]">
              {status === "running" ? "Live Feed" : "Crawled Pages"}
            </div>
            {status === "running" && (
              <div className="w-1 h-1 rounded-full bg-[#7b8ff5] animate-pulse" />
            )}
            <div className="text-[10px] text-[#333] font-mono ml-auto">
              click to expand
            </div>
          </div>
          <div
            ref={listRef}
            className="max-h-[360px] overflow-y-auto border border-[#1a1a1a] rounded-lg p-1.5 space-y-px"
          >
            {pages.map((page, i) => (
              <PageRow key={page.url} page={page} index={i} />
            ))}
          </div>
          <div className="text-[10px] text-[#333] mt-2 font-mono">
            {pages.length} pages streamed
          </div>
        </div>
      )}

      {/* Error */}
      {(error || job.error_message) && (
        <div className="py-3 px-4 border border-red-500/20 rounded-lg text-red-400/80 text-xs">
          {error || job.error_message}
        </div>
      )}
    </div>
  );
}
