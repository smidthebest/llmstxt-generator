import { CrawlJob } from "../api/client";

interface Props {
  job: CrawlJob | undefined;
  isLoading: boolean;
}

export default function CrawlProgress({ job, isLoading }: Props) {
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

  const status = job.status;
  const progress =
    job.pages_found > 0
      ? Math.round((job.pages_crawled / job.pages_found) * 100)
      : 0;

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
          <span className="text-xs font-mono text-[#7b8ff5]">{progress}%</span>
        )}
      </div>

      {/* Bar */}
      {(status === "running" || status === "pending") && (
        <div className="w-full h-px bg-[#222] rounded-full overflow-hidden">
          {status === "running" ? (
            <div
              className="h-full rounded-full bar-anim transition-all duration-500"
              style={{ width: `${Math.max(progress, 3)}%` }}
            />
          ) : (
            <div className="h-full w-full anim-shimmer rounded-full" />
          )}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Found", value: job.pages_found },
          { label: "Crawled", value: job.pages_crawled },
          { label: "Changed", value: job.pages_changed },
        ].map((s) => (
          <div key={s.label} className="py-3">
            <div className="text-xl font-mono text-[#f0f0f0]">{s.value}</div>
            <div className="text-[10px] tracking-[0.15em] uppercase text-[#ccc] mt-1">
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {job.error_message && (
        <div className="py-3 px-4 border border-red-500/20 rounded-lg text-red-400/80 text-xs">
          {job.error_message}
        </div>
      )}
    </div>
  );
}
