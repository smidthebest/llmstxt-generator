import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useSites } from "../hooks/useSites";
import { deleteSite } from "../api/client";

export default function HistoryPage() {
  const { data: sites, isLoading } = useSites();
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: deleteSite,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sites"] }),
  });

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 anim-enter">
      <h1 className="font-display text-3xl font-bold mb-8">Sites</h1>

      {isLoading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg anim-shimmer" />
          ))}
        </div>
      )}

      {sites && sites.length === 0 && (
        <div className="py-20 text-center">
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
        <div className="border-t border-[#383838]">
          <div className="stagger">
            {sites.map((site) => (
              <div
                key={site.id}
                className="flex items-center justify-between py-4 border-b border-[#383838] group"
              >
                <Link to={`/sites/${site.id}`} className="flex-1 min-w-0">
                  <span className="text-sm text-[#ccc] group-hover:text-white transition-colors">
                    {site.domain}
                  </span>
                  {site.title && (
                    <span className="text-xs text-[#ccc] ml-3 hidden sm:inline">
                      {site.title}
                    </span>
                  )}
                </Link>
                <div className="flex items-center gap-4 ml-4 shrink-0">
                  <span className="text-[10px] text-[#bbb] tracking-wider font-mono">
                    {new Date(site.created_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={() => {
                      if (confirm("Delete this site and all its data?")) {
                        deleteMutation.mutate(site.id);
                      }
                    }}
                    className="text-[10px] tracking-widest uppercase text-[#bbb] hover:text-red-400 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
