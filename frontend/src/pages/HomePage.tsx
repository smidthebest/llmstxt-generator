import { Link } from "react-router-dom";
import UrlInput from "../components/UrlInput";
import { useSites } from "../hooks/useSites";

export default function HomePage() {
  const { data: sites, isLoading } = useSites();

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50">
        <div className="max-w-3xl mx-auto px-6 h-12 flex items-center justify-between">
          <span className="font-display text-lg font-bold text-[#f0f0f0]">
            llms.txt
          </span>
          <Link
            to="/history"
            className="text-xs tracking-widest uppercase text-[#666] hover:text-[#f0f0f0] transition-colors"
          >
            Sites
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-24">
        <div className="anim-enter text-center mb-12">
          <h1 className="font-display text-6xl sm:text-7xl font-bold tracking-tight mb-3 text-[#f0f0f0]">
            llms.txt
          </h1>
          <p className="text-[#666] text-sm tracking-wide">
            Crawl any website. Generate a structured llms.txt file.
          </p>
        </div>

        <div className="w-full max-w-lg anim-enter" style={{ animationDelay: "150ms" }}>
          <UrlInput />
        </div>

        {!isLoading && sites && sites.length > 0 && (
          <div
            className="mt-20 w-full max-w-lg anim-enter"
            style={{ animationDelay: "300ms" }}
          >
            <div className="text-[10px] tracking-[0.2em] uppercase text-[#555] mb-4">
              Recent
            </div>
            <div className="space-y-px stagger">
              {sites.slice(0, 5).map((site) => (
                <Link
                  key={site.id}
                  to={`/sites/${site.id}`}
                  className="flex items-center justify-between py-3 px-4 -mx-4 rounded-lg hover:bg-[#0a0a0a] transition-colors group"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-[#ccc] group-hover:text-white transition-colors truncate">
                      {site.domain}
                    </div>
                    {site.title && (
                      <div className="text-xs text-[#555] truncate mt-0.5">
                        {site.title}
                      </div>
                    )}
                  </div>
                  <span className="text-[#333] group-hover:text-[#7b8ff5] transition-colors ml-4 shrink-0">
                    &rarr;
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
