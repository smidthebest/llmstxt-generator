import { Link } from "react-router-dom";
import UrlInput from "../components/UrlInput";
import { useSites } from "../hooks/useSites";

export default function HomePage() {
  const { data: sites, isLoading } = useSites();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold mb-2">llms.txt Generator</h1>
        <p className="text-gray-600">
          Generate llms.txt files for any website automatically
        </p>
      </div>

      <UrlInput />

      {!isLoading && sites && sites.length > 0 && (
        <div className="mt-12 w-full max-w-xl">
          <h2 className="text-lg font-semibold mb-3 text-gray-700">
            Recent Sites
          </h2>
          <div className="space-y-2">
            {sites.slice(0, 10).map((site) => (
              <Link
                key={site.id}
                to={`/sites/${site.id}`}
                className="block p-3 bg-white rounded-lg border hover:border-blue-300 transition-colors"
              >
                <div className="font-medium text-blue-600">{site.domain}</div>
                {site.title && (
                  <div className="text-sm text-gray-500">{site.title}</div>
                )}
              </Link>
            ))}
          </div>
          <Link
            to="/history"
            className="inline-block mt-4 text-sm text-blue-600 hover:underline"
          >
            View all sites
          </Link>
        </div>
      )}
    </div>
  );
}
