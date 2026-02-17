import { useState } from "react";
import { CrawlConfig } from "../api/client";

interface Props {
  onChange: (config: CrawlConfig) => void;
}

export default function CrawlConfigPanel({ onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxPages, setMaxPages] = useState(200);

  const handleDepth = (v: number) => {
    setMaxDepth(v);
    onChange({ max_depth: v, max_pages: maxPages });
  };

  const handlePages = (v: number) => {
    setMaxPages(v);
    onChange({ max_depth: maxDepth, max_pages: v });
  };

  return (
    <div className="border border-[#383838] rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 text-[10px] tracking-[0.15em] uppercase text-[#ccc] hover:text-[#f0f0f0] transition-colors"
      >
        <span>Advanced Settings</span>
        <span
          className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        >
          &#9662;
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 space-y-4 anim-enter">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] tracking-[0.15em] uppercase text-[#ccc]">
                Max Depth
              </label>
              <span className="text-xs font-mono text-[#7b8ff5]">
                {maxDepth}
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={5}
              value={maxDepth}
              onChange={(e) => handleDepth(Number(e.target.value))}
              className="w-full h-1 bg-[#222] rounded-full appearance-none cursor-pointer accent-[#7b8ff5]"
            />
            <div className="flex justify-between text-[9px] text-[#aaa] mt-0.5">
              <span>1 (shallow)</span>
              <span>5 (deep)</span>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] tracking-[0.15em] uppercase text-[#ccc]">
                Max Pages
              </label>
              <span className="text-xs font-mono text-[#7b8ff5]">
                {maxPages}
              </span>
            </div>
            <input
              type="range"
              min={50}
              max={500}
              step={50}
              value={maxPages}
              onChange={(e) => handlePages(Number(e.target.value))}
              className="w-full h-1 bg-[#222] rounded-full appearance-none cursor-pointer accent-[#7b8ff5]"
            />
            <div className="flex justify-between text-[9px] text-[#aaa] mt-0.5">
              <span>50</span>
              <span>500</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
