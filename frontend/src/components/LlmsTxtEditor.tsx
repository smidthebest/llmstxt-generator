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
    mutationFn: (c: string) => updateLlmsTxt(siteId, c),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llmstxt", siteId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  return (
    <div className="space-y-3 anim-enter">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        className="w-full h-[500px] p-5 font-mono text-sm bg-transparent border border-[#1a1a1a] rounded-lg text-[#ccc] placeholder-[#444] focus:outline-none focus:border-[#7b8ff5]/50 transition-colors resize-y leading-relaxed"
        spellCheck={false}
      />
      <div className="flex items-center gap-3">
        <button
          onClick={() => mutation.mutate(content)}
          disabled={mutation.isPending}
          className="px-4 py-2 bg-[#f0f0f0] text-black rounded-md text-xs font-medium hover:bg-white disabled:opacity-40 transition-colors"
        >
          {mutation.isPending ? "Saving..." : "Save"}
        </button>
        {saved && (
          <span className="text-[#4ade80] text-xs anim-enter">Saved</span>
        )}
        {mutation.isError && (
          <span className="text-red-400/80 text-xs anim-enter">
            Failed to save
          </span>
        )}
      </div>
    </div>
  );
}
