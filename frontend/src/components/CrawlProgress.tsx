import { CrawlJob } from "../api/client";

interface Props {
  job: CrawlJob | undefined;
  isLoading: boolean;
}

export default function CrawlProgress({ job, isLoading }: Props) {
  if (isLoading || !job) {
    return <div className="text-gray-500">Loading crawl status...</div>;
  }

  const statusColors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    running: "bg-blue-100 text-blue-800",
    completed: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  const progress =
    job.pages_found > 0
      ? Math.round((job.pages_crawled / job.pages_found) * 100)
      : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span
          className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors[job.status] || ""}`}
        >
          {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
        </span>
        {job.status === "running" && (
          <span className="text-sm text-gray-500 animate-pulse">
            Crawling...
          </span>
        )}
      </div>

      {job.status === "running" && (
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-blue-600 h-3 rounded-full transition-all duration-300"
            style={{ width: `${Math.max(progress, 5)}%` }}
          />
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="bg-white p-3 rounded-lg border">
          <div className="text-2xl font-bold text-blue-600">
            {job.pages_found}
          </div>
          <div className="text-xs text-gray-500">Pages Found</div>
        </div>
        <div className="bg-white p-3 rounded-lg border">
          <div className="text-2xl font-bold text-green-600">
            {job.pages_crawled}
          </div>
          <div className="text-xs text-gray-500">Pages Crawled</div>
        </div>
        <div className="bg-white p-3 rounded-lg border">
          <div className="text-2xl font-bold text-orange-600">
            {job.pages_changed}
          </div>
          <div className="text-xs text-gray-500">Pages Changed</div>
        </div>
      </div>

      {job.error_message && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {job.error_message}
        </div>
      )}
    </div>
  );
}
