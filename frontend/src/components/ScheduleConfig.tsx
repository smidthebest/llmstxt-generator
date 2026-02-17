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
    mutationFn: () =>
      upsertSchedule(siteId, PRESETS[frequency], isActive),
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
    <div className="space-y-4 bg-white p-6 rounded-lg border">
      <h3 className="text-lg font-semibold">Monitoring Schedule</h3>

      {schedule && (
        <div className="text-sm text-gray-600">
          Current: <code className="bg-gray-100 px-1 rounded">{schedule.cron_expression}</code>
          {" "}({schedule.is_active ? "Active" : "Paused"})
          {schedule.last_run_at && (
            <span> | Last run: {new Date(schedule.last_run_at).toLocaleString()}</span>
          )}
        </div>
      )}

      <div className="flex items-center gap-4">
        <select
          value={frequency}
          onChange={(e) => setFrequency(e.target.value)}
          className="px-3 py-2 border rounded-lg"
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="w-4 h-4"
          />
          Active
        </label>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving..." : "Save Schedule"}
        </button>
        {schedule && (
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            className="px-4 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100"
          >
            Remove
          </button>
        )}
        {saved && <span className="self-center text-green-600 text-sm">Saved!</span>}
      </div>
    </div>
  );
}
