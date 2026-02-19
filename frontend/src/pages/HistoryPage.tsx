import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteSite, SiteOverview, startCrawl } from "../api/client";
import { useSitesOverview } from "../hooks/useSitesOverview";

const ACTIVE_STATUSES = new Set(["pending", "running", "generating"]);

function formatRelative(value: string | null): string {
  if (!value) return "--";
  const diffMs = Date.now() - new Date(value).getTime();
  if (diffMs < 60_000) return "just now";
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function statusUi(status: SiteOverview["latest_crawl_status"]) {
  switch (status) {
    case "pending":
      return {
        label: "Queued",
        className: "text-[#f0f0f0] bg-[#161616] border-[#3a3a3a]",
      };
    case "running":
      return {
        label: "Crawling",
        className: "text-[#7b8ff5] bg-[#11162a] border-[#2a3362]",
      };
    case "generating":
      return {
        label: "Generating",
        className: "text-[#f59e0b] bg-[#211707] border-[#5a3a12]",
      };
    case "completed":
      return {
        label: "Completed",
        className: "text-[#4ade80] bg-[#0d1f14] border-[#1f4d2f]",
      };
    case "failed":
      return {
        label: "Failed",
        className: "text-red-300 bg-[#2a1111] border-[#643636]",
      };
    default:
      return {
        label: "Not Crawled",
        className: "text-[#bbb] bg-[#141414] border-[#303030]",
      };
  }
}

function scheduleUi(row: SiteOverview) {
  if (!row.schedule_cron_expression) {
    return { label: "Not set", detail: "--", tone: "text-[#888]" };
  }
  if (row.schedule_active) {
    return {
      label: "Active",
      detail: row.schedule_next_run_at
        ? `Next ${formatRelative(row.schedule_next_run_at)}`
        : "Next run pending",
      tone: "text-[#4ade80]",
    };
  }
  return { label: "Paused", detail: "Configured", tone: "text-[#f59e0b]" };
}

function llmsUi(row: SiteOverview) {
  if (row.llms_generated) {
    return {
      label: row.llms_edited ? "Edited" : "Ready",
      detail: formatRelative(row.llms_generated_at),
      tone: row.llms_edited ? "text-[#f59e0b]" : "text-[#4ade80]",
    };
  }
  if (row.latest_crawl_status && ACTIVE_STATUSES.has(row.latest_crawl_status)) {
    return { label: "Pending", detail: "Crawl in progress", tone: "text-[#7b8ff5]" };
  }
  if (row.latest_crawl_status === "failed") {
    return { label: "Unavailable", detail: "Last crawl failed", tone: "text-red-300" };
  }
  return { label: "Not generated", detail: "--", tone: "text-[#888]" };
}

export default function HistoryPage() {
  const { data: sites, isLoading } = useSitesOverview();
  const queryClient = useQueryClient();
  const [activeRecrawlSiteId, setActiveRecrawlSiteId] = useState<number | null>(null);
  const [activeDeleteSiteId, setActiveDeleteSiteId] = useState<number | null>(null);

  const deleteMutation = useMutation({
    mutationFn: deleteSite,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      queryClient.invalidateQueries({ queryKey: ["sitesOverview"] });
    },
  });

  const recrawlMutation = useMutation({
    mutationFn: (siteId: number) => startCrawl(siteId),
    onSuccess: (_job, siteId) => {
      queryClient.invalidateQueries({ queryKey: ["sitesOverview"] });
      queryClient.invalidateQueries({ queryKey: ["crawlJobs", siteId] });
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
    },
  });

  const stats = useMemo(() => {
    const rows = sites ?? [];
    const total = rows.length;
    const crawled = rows.filter((row) => row.latest_crawl_status === "completed").length;
    const running = rows.filter(
      (row) => row.latest_crawl_status && ACTIVE_STATUSES.has(row.latest_crawl_status)
    ).length;
    const ready = rows.filter((row) => row.llms_generated).length;
    const failed = rows.filter((row) => row.latest_crawl_status === "failed").length;
    return { total, crawled, running, ready, failed };
  }, [sites]);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10 anim-enter">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold text-[#f0f0f0]">Sites</h1>
          <p className="text-xs tracking-wider text-[#bbb] mt-2">
            Manage crawl state, generation status, and monitoring actions.
          </p>
        </div>
        <Link
          to="/"
          className="text-xs tracking-widest uppercase text-[#ccc] hover:text-[#f0f0f0] border border-[#444] hover:border-[#555] px-3 py-2 rounded-md transition-all"
        >
          + Add Site
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-7">
        {[
          { label: "Total Sites", value: stats.total, tone: "text-[#f0f0f0]" },
          { label: "Crawled", value: stats.crawled, tone: "text-[#4ade80]" },
          { label: "Running", value: stats.running, tone: "text-[#7b8ff5]" },
          { label: "llms.txt Ready", value: stats.ready, tone: "text-[#f59e0b]" },
          { label: "Failed", value: stats.failed, tone: "text-red-300" },
        ].map((stat) => (
          <div key={stat.label} className="border border-[#383838] rounded-lg px-4 py-3">
            <div className={`text-2xl font-mono ${stat.tone}`}>{stat.value}</div>
            <div className="text-[10px] tracking-[0.15em] uppercase text-[#999] mt-1">
              {stat.label}
            </div>
          </div>
        ))}
      </div>

      {stats.running > 0 && (
        <div className="flex items-center gap-2 text-[11px] tracking-wider uppercase text-[#7b8ff5] mb-4">
          <span className="w-1.5 h-1.5 rounded-full bg-[#7b8ff5] animate-pulse" />
          Live updates enabled
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-lg anim-shimmer" />
          ))}
        </div>
      )}

      {sites && sites.length === 0 && (
        <div className="py-20 text-center border border-[#383838] rounded-xl">
          <p className="text-[#ccc] mb-4">No sites yet.</p>
          <Link
            to="/"
            className="inline-block px-5 py-2 text-sm border border-[#444] text-[#ccc] rounded-lg hover:bg-[#111] hover:border-[#555] transition-all"
          >
            Generate your first llms.txt
          </Link>
        </div>
      )}

      {sites && sites.length > 0 && (
        <div className="border border-[#383838] rounded-xl overflow-x-auto">
          <table className="w-full text-left min-w-[1050px]">
            <thead className="bg-[#0d0d0d] border-b border-[#383838]">
              <tr className="text-[10px] tracking-[0.16em] uppercase text-[#999]">
                <th className="px-4 py-3 font-medium">Site</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last Crawl</th>
                <th className="px-4 py-3 font-medium">llms.txt</th>
                <th className="px-4 py-3 font-medium">Schedule</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="stagger">
              {sites.map((row) => {
                const status = statusUi(row.latest_crawl_status);
                const llms = llmsUi(row);
                const schedule = scheduleUi(row);
                const isBusyRecrawling = activeRecrawlSiteId === row.site.id;
                const isBusyDeleting = activeDeleteSiteId === row.site.id;
                const isCrawlActive =
                  row.latest_crawl_status && ACTIVE_STATUSES.has(row.latest_crawl_status);

                return (
                  <tr
                    key={row.site.id}
                    className="border-b border-[#262626] hover:bg-[#0a0a0a] transition-colors"
                  >
                    <td className="px-4 py-4 align-top">
                      <Link
                        to={`/sites/${row.site.id}`}
                        className="text-sm text-[#e6e6e6] hover:text-white transition-colors"
                      >
                        {row.site.domain}
                      </Link>
                      <div className="text-[11px] text-[#888] mt-1 truncate max-w-[280px] font-mono">
                        {row.site.url}
                      </div>
                      {row.site.title && (
                        <div className="text-xs text-[#bbb] mt-1 truncate max-w-[340px]">
                          {row.site.title}
                        </div>
                      )}
                    </td>

                    <td className="px-4 py-4 align-top">
                      <span
                        className={`inline-flex items-center px-2 py-1 text-[10px] tracking-wide uppercase rounded-full border ${status.className}`}
                      >
                        {status.label}
                      </span>
                      {row.latest_crawl_updated_at && (
                        <div className="text-[11px] text-[#888] mt-2">
                          {formatRelative(row.latest_crawl_updated_at)}
                        </div>
                      )}
                      {row.latest_crawl_error_message && (
                        <div
                          className="text-[11px] text-red-300 mt-2 max-w-[220px] truncate"
                          title={row.latest_crawl_error_message}
                        >
                          {row.latest_crawl_error_message}
                        </div>
                      )}
                    </td>

                    <td className="px-4 py-4 align-top">
                      <div className="text-sm text-[#f0f0f0] font-mono">
                        {row.latest_crawl_pages_crawled ?? 0} / {row.latest_crawl_pages_found ?? 0}
                      </div>
                      <div className="text-[11px] text-[#999] mt-1">
                        Crawled / Found
                      </div>
                      <div className="text-[11px] text-[#bbb] mt-2">
                        Changed:{" "}
                        <span className="font-mono text-[#f0f0f0]">
                          {row.latest_crawl_pages_changed ?? 0}
                        </span>
                      </div>
                    </td>

                    <td className="px-4 py-4 align-top">
                      <div className={`text-xs uppercase tracking-wide ${llms.tone}`}>
                        {llms.label}
                      </div>
                      <div className="text-[11px] text-[#999] mt-2">{llms.detail}</div>
                    </td>

                    <td className="px-4 py-4 align-top">
                      <div className={`text-xs uppercase tracking-wide ${schedule.tone}`}>
                        {schedule.label}
                      </div>
                      <div className="text-[11px] text-[#999] mt-2">{schedule.detail}</div>
                      {row.schedule_cron_expression && (
                        <code className="inline-block text-[10px] text-[#aaa] bg-[#141414] border border-[#2f2f2f] rounded px-2 py-1 mt-2">
                          {row.schedule_cron_expression}
                        </code>
                      )}
                    </td>

                    <td className="px-4 py-4 align-top">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          to={`/sites/${row.site.id}`}
                          className="text-[10px] tracking-widest uppercase text-[#ccc] hover:text-white border border-[#444] hover:border-[#555] px-2.5 py-1.5 rounded transition-all"
                        >
                          Open
                        </Link>
                        <button
                          onClick={() => {
                            setActiveRecrawlSiteId(row.site.id);
                            recrawlMutation.mutate(row.site.id, {
                              onSettled: () => setActiveRecrawlSiteId(null),
                            });
                          }}
                          disabled={Boolean(isCrawlActive) || isBusyRecrawling || isBusyDeleting}
                          className="text-[10px] tracking-widest uppercase text-[#7b8ff5] hover:text-[#9cadff] border border-[#2f3a72] hover:border-[#4350a0] px-2.5 py-1.5 rounded transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {isBusyRecrawling ? "Queued..." : "Re-crawl"}
                        </button>
                        <Link
                          to={`/sites/${row.site.id}?tab=schedule`}
                          className="text-[10px] tracking-widest uppercase text-[#f59e0b] hover:text-[#f7b84a] border border-[#5c3d1a] hover:border-[#7a5323] px-2.5 py-1.5 rounded transition-all"
                        >
                          Schedule
                        </Link>
                        <button
                          onClick={() => {
                            if (!confirm("Delete this site and all its data?")) return;
                            setActiveDeleteSiteId(row.site.id);
                            deleteMutation.mutate(row.site.id, {
                              onSettled: () => setActiveDeleteSiteId(null),
                            });
                          }}
                          disabled={isBusyDeleting || isBusyRecrawling}
                          className="text-[10px] tracking-widest uppercase text-red-300 hover:text-red-200 border border-[#5f3232] hover:border-[#7f4343] px-2.5 py-1.5 rounded transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {isBusyDeleting ? "Deleting..." : "Delete"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
