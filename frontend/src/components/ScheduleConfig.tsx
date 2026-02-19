import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSchedule,
  upsertSchedule,
  deleteSchedule,
  startCrawl,
  Schedule,
} from "../api/client";

type Frequency = "hourly" | "daily" | "weekly" | "monthly";

const DAYS_OF_WEEK = [
  { value: 0, label: "Sun" },
  { value: 1, label: "Mon" },
  { value: 2, label: "Tue" },
  { value: 3, label: "Wed" },
  { value: 4, label: "Thu" },
  { value: 5, label: "Fri" },
  { value: 6, label: "Sat" },
];

const HOUR_INTERVALS = [1, 2, 3, 4, 6, 8, 12];

function buildCron(
  freq: Frequency,
  hour: number,
  minute: number,
  dayOfWeek: number,
  dayOfMonth: number,
  hourInterval: number
): string {
  switch (freq) {
    case "hourly":
      return `${minute} */${hourInterval} * * *`;
    case "daily":
      return `${minute} ${hour} * * *`;
    case "weekly":
      return `${minute} ${hour} * * ${dayOfWeek}`;
    case "monthly":
      return `${minute} ${hour} ${dayOfMonth} * *`;
  }
}

function parseCron(cron: string): {
  freq: Frequency;
  hour: number;
  minute: number;
  dayOfWeek: number;
  dayOfMonth: number;
  hourInterval: number;
} {
  const parts = cron.split(" ");
  if (parts.length !== 5)
    return { freq: "daily", hour: 0, minute: 0, dayOfWeek: 0, dayOfMonth: 1, hourInterval: 6 };

  const [minStr, hourStr, domStr, , dowStr] = parts;
  const minute = parseInt(minStr) || 0;

  if (hourStr.startsWith("*/")) {
    return { freq: "hourly", hour: 0, minute, dayOfWeek: 0, dayOfMonth: 1, hourInterval: parseInt(hourStr.slice(2)) || 6 };
  }
  if (dowStr !== "*") {
    return { freq: "weekly", hour: parseInt(hourStr) || 0, minute, dayOfWeek: parseInt(dowStr) || 0, dayOfMonth: 1, hourInterval: 6 };
  }
  if (domStr !== "*") {
    return { freq: "monthly", hour: parseInt(hourStr) || 0, minute, dayOfWeek: 0, dayOfMonth: parseInt(domStr) || 1, hourInterval: 6 };
  }
  return { freq: "daily", hour: parseInt(hourStr) || 0, minute, dayOfWeek: 0, dayOfMonth: 1, hourInterval: 6 };
}

function describeSchedule(
  freq: Frequency,
  hour: number,
  minute: number,
  dayOfWeek: number,
  dayOfMonth: number,
  hourInterval: number
): string {
  const time = `${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")} UTC`;
  switch (freq) {
    case "hourly":
      return `Every ${hourInterval} hour${hourInterval > 1 ? "s" : ""} at :${minute.toString().padStart(2, "0")}`;
    case "daily":
      return `Every day at ${time}`;
    case "weekly":
      return `Every ${DAYS_OF_WEEK[dayOfWeek].label} at ${time}`;
    case "monthly":
      return `Monthly on the ${ordinal(dayOfMonth)} at ${time}`;
  }
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function timeUntil(dateStr: string): string {
  const diff = new Date(dateStr).getTime() - Date.now();
  if (diff <= 0) return "due now";
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `in ${hours}h ${mins % 60}m`;
  const days = Math.floor(hours / 24);
  return `in ${days}d ${hours % 24}h`;
}

function timeSince(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 60_000) return "just now";
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ${mins % 60}m ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h ago`;
}

interface Props {
  siteId: number;
  onCrawlStarted?: (jobId: number) => void;
  latestCrawlAt?: string | null;
}

export default function ScheduleConfig({ siteId, onCrawlStarted, latestCrawlAt }: Props) {
  const queryClient = useQueryClient();

  const [freq, setFreq] = useState<Frequency>("daily");
  const [hour, setHour] = useState(0);
  const [minute, setMinute] = useState(0);
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [dayOfMonth, setDayOfMonth] = useState(1);
  const [hourInterval, setHourInterval] = useState(6);
  const [isActive, setIsActive] = useState(true);
  const [saved, setSaved] = useState(false);
  const [initialized, setInitialized] = useState(false);

  const { data: schedule } = useQuery<Schedule>({
    queryKey: ["schedule", siteId],
    queryFn: () => getSchedule(siteId),
    retry: false,
    refetchInterval: 30000,
  });

  // Seed form from existing schedule
  useEffect(() => {
    if (schedule && !initialized) {
      const parsed = parseCron(schedule.cron_expression);
      setFreq(parsed.freq);
      setHour(parsed.hour);
      setMinute(parsed.minute);
      setDayOfWeek(parsed.dayOfWeek);
      setDayOfMonth(parsed.dayOfMonth);
      setHourInterval(parsed.hourInterval);
      setIsActive(schedule.is_active);
      setInitialized(true);
    }
  }, [schedule, initialized]);

  const cronExpression = useMemo(
    () => buildCron(freq, hour, minute, dayOfWeek, dayOfMonth, hourInterval),
    [freq, hour, minute, dayOfWeek, dayOfMonth, hourInterval]
  );

  const description = useMemo(
    () => describeSchedule(freq, hour, minute, dayOfWeek, dayOfMonth, hourInterval),
    [freq, hour, minute, dayOfWeek, dayOfMonth, hourInterval]
  );

  const saveMutation = useMutation({
    mutationFn: () => upsertSchedule(siteId, cronExpression, isActive),
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
      setInitialized(false);
    },
  });

  const runNowMutation = useMutation({
    mutationFn: () => startCrawl(siteId),
    onSuccess: (job) => {
      queryClient.setQueryData(["crawl", siteId, job.id], job);
      queryClient.invalidateQueries({ queryKey: ["crawlJobs", siteId] });
      onCrawlStarted?.(job.id);
    },
  });

  return (
    <div className="space-y-6 anim-enter">
      {/* Current schedule status card */}
      {schedule && (
        <div className="border border-[#333] rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-2.5 h-2.5 rounded-full ${
                  schedule.is_active
                    ? "bg-[#4ade80] shadow-[0_0_8px_rgba(74,222,128,0.4)]"
                    : "bg-[#555]"
                }`}
              />
              <span className="text-sm font-medium text-[#f0f0f0]">
                {schedule.is_active ? "Active" : "Paused"}
              </span>
            </div>
            <code className="text-[10px] font-mono text-[#888] bg-[#1a1a1a] px-2 py-1 rounded">
              {schedule.cron_expression}
            </code>
          </div>

          <p className="text-sm text-[#ccc]">
            {describeSchedule(
              ...Object.values(parseCron(schedule.cron_expression)) as [Frequency, number, number, number, number, number]
            )}
          </p>

          <div className="grid grid-cols-2 gap-4 pt-1">
            <div>
              <span className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-1">
                Next run
              </span>
              {schedule.next_run_at ? (
                <div>
                  <span className="text-sm text-[#f0f0f0] font-mono">
                    {timeUntil(schedule.next_run_at)}
                  </span>
                  <span className="block text-[10px] text-[#888] font-mono mt-0.5">
                    {new Date(schedule.next_run_at).toLocaleString()}
                  </span>
                </div>
              ) : (
                <span className="text-sm text-[#555]">--</span>
              )}
            </div>
            <div>
              <span className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-1">
                Last crawl
              </span>
              {(() => {
                // Show the most recent crawl time, whether scheduled or ad-hoc
                const candidates = [schedule.last_run_at, latestCrawlAt].filter(Boolean) as string[];
                const latest = candidates.length > 0
                  ? candidates.reduce((a, b) => new Date(a) > new Date(b) ? a : b)
                  : null;
                return latest ? (
                  <div>
                    <span className="text-sm text-[#f0f0f0] font-mono">
                      {timeSince(latest)}
                    </span>
                    <span className="block text-[10px] text-[#888] font-mono mt-0.5">
                      {new Date(latest).toLocaleString()}
                    </span>
                  </div>
                ) : (
                  <span className="text-sm text-[#555]">Never</span>
                );
              })()}
            </div>
          </div>

          <div className="pt-2 border-t border-[#2a2a2a]">
            <button
              onClick={() => runNowMutation.mutate()}
              disabled={runNowMutation.isPending}
              className="text-xs tracking-widest uppercase text-[#7b8ff5] hover:text-[#99abff] disabled:opacity-40 transition-colors"
            >
              {runNowMutation.isPending ? "Triggering..." : "Run now"}
            </button>
            {runNowMutation.isSuccess && (
              <span className="text-[#4ade80] text-xs ml-3 anim-enter">
                Crawl started
              </span>
            )}
          </div>
        </div>
      )}

      {/* Configuration form */}
      <div className="border border-[#333] rounded-lg p-5 space-y-5">
        <h3 className="text-xs tracking-[0.15em] uppercase text-[#999] font-medium">
          {schedule ? "Update schedule" : "Create schedule"}
        </h3>

        {/* Frequency selector */}
        <div>
          <label className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-2">
            Frequency
          </label>
          <div className="flex gap-1.5">
            {(["hourly", "daily", "weekly", "monthly"] as Frequency[]).map(
              (f) => (
                <button
                  key={f}
                  onClick={() => setFreq(f)}
                  className={`px-3 py-1.5 text-xs rounded-md border transition-all ${
                    freq === f
                      ? "bg-[#7b8ff5] border-[#7b8ff5] text-white"
                      : "border-[#444] text-[#ccc] hover:border-[#555] hover:text-[#f0f0f0]"
                  }`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              )
            )}
          </div>
        </div>

        {/* Hourly interval */}
        {freq === "hourly" && (
          <div>
            <label className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-2">
              Every
            </label>
            <div className="flex gap-1.5 flex-wrap">
              {HOUR_INTERVALS.map((h) => (
                <button
                  key={h}
                  onClick={() => setHourInterval(h)}
                  className={`px-3 py-1.5 text-xs rounded-md border transition-all ${
                    hourInterval === h
                      ? "bg-[#7b8ff5] border-[#7b8ff5] text-white"
                      : "border-[#444] text-[#ccc] hover:border-[#555] hover:text-[#f0f0f0]"
                  }`}
                >
                  {h}h
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Day of week for weekly */}
        {freq === "weekly" && (
          <div>
            <label className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-2">
              Day
            </label>
            <div className="flex gap-1.5">
              {DAYS_OF_WEEK.map((d) => (
                <button
                  key={d.value}
                  onClick={() => setDayOfWeek(d.value)}
                  className={`w-10 py-1.5 text-xs rounded-md border transition-all ${
                    dayOfWeek === d.value
                      ? "bg-[#7b8ff5] border-[#7b8ff5] text-white"
                      : "border-[#444] text-[#ccc] hover:border-[#555] hover:text-[#f0f0f0]"
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Day of month for monthly */}
        {freq === "monthly" && (
          <div>
            <label className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-2">
              Day of month
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={1}
                max={28}
                value={dayOfMonth}
                onChange={(e) => setDayOfMonth(Number(e.target.value))}
                className="flex-1 accent-[#7b8ff5]"
              />
              <span className="text-sm font-mono text-[#f0f0f0] w-8 text-right">
                {ordinal(dayOfMonth)}
              </span>
            </div>
          </div>
        )}

        {/* Time picker (not shown for hourly) */}
        {freq !== "hourly" ? (
          <div>
            <label className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-2">
              Time (UTC)
            </label>
            <div className="flex items-center gap-2">
              <select
                value={hour}
                onChange={(e) => setHour(Number(e.target.value))}
                className="px-3 py-2 bg-[#1a1a1a] border border-[#444] rounded-md text-sm text-[#f0f0f0] font-mono focus:outline-none focus:border-[#7b8ff5] w-20"
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>
                    {i.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
              <span className="text-[#666] text-lg">:</span>
              <select
                value={minute}
                onChange={(e) => setMinute(Number(e.target.value))}
                className="px-3 py-2 bg-[#1a1a1a] border border-[#444] rounded-md text-sm text-[#f0f0f0] font-mono focus:outline-none focus:border-[#7b8ff5] w-20"
              >
                {[0, 15, 30, 45].map((m) => (
                  <option key={m} value={m}>
                    {m.toString().padStart(2, "0")}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <div>
            <label className="text-[10px] tracking-[0.15em] uppercase text-[#888] block mb-2">
              At minute
            </label>
            <select
              value={minute}
              onChange={(e) => setMinute(Number(e.target.value))}
              className="px-3 py-2 bg-[#1a1a1a] border border-[#444] rounded-md text-sm text-[#f0f0f0] font-mono focus:outline-none focus:border-[#7b8ff5] w-20"
            >
              {[0, 15, 30, 45].map((m) => (
                <option key={m} value={m}>
                  :{m.toString().padStart(2, "0")}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Active toggle */}
        <div className="flex items-center justify-between">
          <label
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => setIsActive(!isActive)}
          >
            <div className="relative">
              <div
                className={`w-9 h-5 rounded-full transition-colors ${
                  isActive ? "bg-[#7b8ff5]" : "bg-[#333]"
                }`}
              />
              <div
                className={`absolute top-[3px] w-3.5 h-3.5 bg-white rounded-full transition-all ${
                  isActive ? "left-[18px]" : "left-[3px]"
                }`}
              />
            </div>
            <span className="text-sm text-[#ccc]">
              {isActive ? "Enabled" : "Disabled"}
            </span>
          </label>
        </div>

        {/* Summary */}
        <div className="bg-[#1a1a1a] rounded-md px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-[#ddd]">{description}</p>
          <code className="text-[10px] font-mono text-[#666] ml-4 shrink-0">
            {cronExpression}
          </code>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="px-5 py-2 bg-[#f0f0f0] text-black rounded-md text-xs font-medium hover:bg-white disabled:opacity-40 transition-colors"
          >
            {saveMutation.isPending
              ? "Saving..."
              : schedule
              ? "Update"
              : "Create"}
          </button>
          {schedule && (
            <button
              onClick={() => {
                if (!confirm("Remove this schedule?")) return;
                deleteMutation.mutate();
              }}
              disabled={deleteMutation.isPending}
              className="text-xs tracking-widest uppercase text-[#888] hover:text-red-400/80 transition-colors"
            >
              Remove
            </button>
          )}
          {saved && (
            <span className="text-[#4ade80] text-xs anim-enter">Saved</span>
          )}
        </div>
      </div>
    </div>
  );
}
