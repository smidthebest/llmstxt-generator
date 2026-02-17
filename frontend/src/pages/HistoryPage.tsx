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
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link to="/" className="text-blue-600 hover:underline text-sm">
        &larr; Back
      </Link>
      <h1 className="text-2xl font-bold mt-4 mb-6">All Sites</h1>

      {isLoading && <div className="text-gray-500">Loading...</div>}

      {sites && sites.length === 0 && (
        <div className="text-gray-500">
          No sites yet.{" "}
          <Link to="/" className="text-blue-600 hover:underline">
            Generate your first llms.txt
          </Link>
        </div>
      )}

      {sites && sites.length > 0 && (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-600">
                <th className="px-4 py-3 font-medium">Domain</th>
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((site) => (
                <tr key={site.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/sites/${site.id}`}
                      className="text-blue-600 hover:underline font-medium"
                    >
                      {site.domain}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {site.title || "-"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(site.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => {
                        if (confirm("Delete this site?")) {
                          deleteMutation.mutate(site.id);
                        }
                      }}
                      className="text-red-600 hover:underline text-xs"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
