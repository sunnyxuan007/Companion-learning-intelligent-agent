"use client";

import { useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";

interface ScheduleEvent {
  date: string;
  label: string;
}

const PROVINCE_SCHEDULES: Record<string, ScheduleEvent[]> = {
  "广东": [
    { date: "2026-06-25", label: "公布成绩和分数线" },
    { date: "2026-06-28", label: "志愿填报开始" },
    { date: "2026-07-04", label: "志愿填报截止" },
    { date: "2026-07-10", label: "提前批录取" },
    { date: "2026-07-18", label: "本科批录取" },
    { date: "2026-08-05", label: "专科批录取" },
  ],
  "江苏": [
    { date: "2026-06-24", label: "公布成绩" },
    { date: "2026-06-28", label: "本科志愿填报开始" },
    { date: "2026-07-02", label: "本科志愿填报截止" },
    { date: "2026-07-08", label: "提前批录取" },
    { date: "2026-07-15", label: "本科批录取" },
  ],
  "浙江": [
    { date: "2026-06-26", label: "公布成绩和分数线" },
    { date: "2026-06-29", label: "志愿填报开始" },
    { date: "2026-06-30", label: "志愿填报截止" },
    { date: "2026-07-11", label: "普通类一段录取" },
    { date: "2026-07-24", label: "普通类二段录取" },
  ],
  "北京": [
    { date: "2026-06-25", label: "公布成绩" },
    { date: "2026-06-27", label: "志愿填报开始" },
    { date: "2026-07-01", label: "志愿填报截止" },
    { date: "2026-07-06", label: "提前批录取" },
    { date: "2026-07-16", label: "本科批录取" },
  ],
  "上海": [
    { date: "2026-06-23", label: "公布成绩和分数线" },
    { date: "2026-06-26", label: "志愿填报开始" },
    { date: "2026-06-30", label: "志愿填报截止" },
    { date: "2026-07-05", label: "强基计划录取" },
    { date: "2026-07-15", label: "本科批录取" },
  ],
};

function daysUntil(target: string): number {
  const now = new Date();
  const targetDate = new Date(target);
  const diff = targetDate.getTime() - now.getTime();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

export default function AdmissionCountdown({ province = "广东" }: { province?: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, []);

  const schedule = PROVINCE_SCHEDULES[province] || PROVINCE_SCHEDULES["广东"];
  const today = new Date().toISOString().slice(0, 10);

  const upcoming = schedule.filter((e) => e.date >= today).slice(0, 3);
  const active = schedule.find((e) => e.date === today);

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <CalendarDays className="h-5 w-5 text-blue-600" />
        <span className="font-semibold text-gray-900">{province} 录取日程</span>
      </div>

      {active && (
        <div className="mb-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">
          今日: {active.label}
        </div>
      )}

      <div className="space-y-2">
        {upcoming.length === 0 && (
          <p className="text-sm text-gray-400">录取工作已全部结束</p>
        )}
        {upcoming.map((event) => {
          const days = daysUntil(event.date);
          return (
            <div key={event.date} className="flex items-center justify-between text-sm">
              <div>
                <span className="text-gray-600">{event.label}</span>
                <span className="ml-2 text-xs text-gray-400">{event.date}</span>
              </div>
              <span
                className={`whitespace-nowrap font-medium ${
                  days <= 3 ? "text-red-500" : days <= 7 ? "text-yellow-600" : "text-gray-500"
                }`}
              >
                {days === 0 ? "今天" : days < 0 ? "已过" : `${days}天`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
