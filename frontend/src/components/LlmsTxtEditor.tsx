import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateLlmsTxt } from "../api/client";

interface Props {
  siteId: number;
  initialContent: string;
}

export default function LlmsTxtEditor({ siteId, initialContent }: Props) {
  const [content, setContent] = useState(initialContent);
  const [saved, setSaved] = useState(false);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (content: string) => updateLlmsTxt(siteId, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llmstxt", siteId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  return (
    <div className="space-y-3">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        className="w-full h-[500px] p-4 font-mono text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
      />
      <div className="flex items-center gap-3">
        <button
          onClick={() => mutation.mutate(content)}
          disabled={mutation.isPending}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {mutation.isPending ? "Saving..." : "Save Changes"}
        </button>
        {saved && <span className="text-green-600 text-sm">Saved!</span>}
        {mutation.isError && (
          <span className="text-red-600 text-sm">Failed to save</span>
        )}
      </div>
    </div>
  );
}
