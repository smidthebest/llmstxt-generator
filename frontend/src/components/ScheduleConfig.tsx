import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSchedule,
  upsertSchedule,
  deleteSchedule,
  Schedule,
} from "../api/client";

const PRESETS: Record<string, string> = {
  daily: "0 0 * * *",
  weekly: "0 0 * * 0",
  monthly: "0 0 1 * *",
};

interface Props {
  siteId: number;
}

export default function ScheduleConfig({ siteId }: Props) {
  const queryClient = useQueryClient();
  const [frequency, setFrequency] = useState("weekly");
  const [isActive, setIsActive] = useState(true);
  const [saved, setSaved] = useState(false);

  const { data: schedule } = useQuery<Schedule>({
    queryKey: ["schedule", siteId],
    queryFn: () => getSchedule(siteId),
    retry: false,
  });

  const saveMutation = useMutation({
    mutationFn: () => upsertSchedule(siteId, PRESETS[frequency], isActive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedule", siteId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteSchedule(siteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedule", siteId] });
    },
  });

  return (
    <div className="space-y-5 anim-enter">
      <h3 className="text-xs tracking-[0.15em] uppercase text-[#888]">
        Monitoring Schedule
      </h3>

      {schedule && (
        <div className="flex items-center gap-3 text-xs">
          <code className="font-mono text-[#ccc]">
            {schedule.cron_expression}
          </code>
          <span className="flex items-center gap-1.5 text-[#555]">
            <span
              className={`w-1.5 h-1.5 rounded-full ${schedule.is_active ? "bg-[#4ade80]" : "bg-[#333]"}`}
            />
            {schedule.is_active ? "Active" : "Paused"}
          </span>
          {schedule.last_run_at && (
            <span className="text-[#444] font-mono">
              {new Date(schedule.last_run_at).toLocaleString()}
            </span>
          )}
        </div>
      )}

      <div className="flex items-center gap-4">
        <select
          value={frequency}
          onChange={(e) => setFrequency(e.target.value)}
          className="px-3 py-2 bg-transparent border border-[#333] rounded-md text-sm text-[#ccc] focus:outline-none focus:border-[#555]"
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>

        <label className="relative inline-flex items-center gap-2 cursor-pointer text-xs text-[#888]">
          <div className="relative">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-8 h-[18px] bg-[#333] rounded-full peer-checked:bg-[#7b8ff5] transition-colors" />
            <div className="absolute left-[3px] top-[3px] w-3 h-3 bg-[#f0f0f0] rounded-full transition-transform peer-checked:translate-x-[14px]" />
          </div>
          Active
        </label>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="px-4 py-2 bg-[#f0f0f0] text-black rounded-md text-xs font-medium hover:bg-white disabled:opacity-40 transition-colors"
        >
          {saveMutation.isPending ? "Saving..." : "Save"}
        </button>
        {schedule && (
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            className="text-xs tracking-widest uppercase text-[#555] hover:text-red-400/80 transition-colors"
          >
            Remove
          </button>
        )}
        {saved && (
          <span className="text-[#4ade80] text-xs anim-enter">Saved</span>
        )}
      </div>
    </div>
  );
}
