"use client";

import { useState, useEffect } from "react";
import { BookOpen, TrendingUp, AlertTriangle, CheckCircle, Calendar, BarChart3, Bell, BellOff, Loader2 } from "lucide-react";

interface CronJob {
  id: string;
  name: string;
  message: string;
  schedule_kind: string;
  next_run_at_ms: number | null;
  enabled: boolean;
}

type ReminderFreq = "off" | "daily" | "weekly";

interface SubjectSummary {
  subject: string;
  count: number;
  avg_accuracy: number | null;
}

interface WeakPoint {
  point: string;
  count: number;
}

interface GapData {
  total_records: number;
  weak_points_ranked: WeakPoint[];
  strong_points_ranked: WeakPoint[];
  suggestion: string;
}

export default function StudyLabPage() {
  const [saving, setSaving] = useState(false);
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [freq, setFreq] = useState<ReminderFreq>("off");
  const [statusMsg, setStatusMsg] = useState("");
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [gapData, setGapData] = useState<GapData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/v1/cron/jobs?user_id=default").then(r => r.json()),
      fetch("/api/v1/study/summary/default").then(r => r.ok ? r.json() : []).catch(() => []),
      fetch("/api/v1/study/gap/default").then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([cronData, subj, gap]) => {
      setJobs(cronData.jobs);
      setSubjects(subj as SubjectSummary[]);
      setGapData(gap as GapData | null);
      const hasWeekly = cronData.jobs.some((j: CronJob) => j.schedule_kind === "cron");
      const hasDaily = cronData.jobs.some(
        (j: CronJob) => j.schedule_kind === "every" && j.message.includes("每天")
      );
      if (hasWeekly) setFreq("weekly");
      else if (hasDaily) setFreq("daily");
      else setFreq("off");
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const setReminder = async (newFreq: ReminderFreq) => {
    setSaving(true);
    setStatusMsg("");
    try {
      for (const job of jobs) {
        await fetch(`/api/v1/cron/jobs/${job.id}?user_id=default`, {
          method: "DELETE",
        });
      }
      if (newFreq !== "off") {
        const payload =
          newFreq === "weekly"
            ? {
                name: "每周学习分析提醒",
                message: "分析我最近一周的学习薄弱点并给出针对性建议",
                session_id: "default",
                user_id: "default",
                schedule: { kind: "cron", expr: "0 9 * * 1", tz: "Asia/Shanghai" },
              }
            : {
                name: "每日学习分析提醒",
                message: "分析我今天的学习薄弱点并给出建议",
                session_id: "default",
                user_id: "default",
                schedule: { kind: "every", every_seconds: 86400 },
              };
        const res = await fetch("/api/v1/cron/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const err = await res.json();
          setStatusMsg(`设置失败: ${err.message}`);
          setSaving(false);
          return;
        }
      }
      setFreq(newFreq);
      setStatusMsg(newFreq === "off" ? "已关闭定时分析" : "已设置定时分析提醒");
    } catch {
      setStatusMsg("网络错误，请重试");
    }
    setSaving(false);
  };

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <BookOpen className="h-6 w-6 text-green-500" />
          学习分析实验室
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          学习记录追踪 · 薄弱知识点分析 · 查缺补漏建议
        </p>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-blue-600">
            <BarChart3 className="h-5 w-5" />
            <span className="font-semibold">学习概览</span>
          </div>
          <p className="mt-2 text-sm text-gray-500">
            查看近期的学习记录和各科正确率趋势
          </p>
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-400">
            <Calendar className="h-3 w-3" />
            <span>请在对话中使用 study_dashboard 工具查看</span>
          </div>
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-semibold">薄弱知识点</span>
          </div>
          <p className="mt-2 text-sm text-gray-500">
            识别高频薄弱知识领域，生成针对性提升计划
          </p>
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-400">
            <Calendar className="h-3 w-3" />
            <span>请在对话中使用 gap_analysis 工具查看</span>
          </div>
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle className="h-5 w-5" />
            <span className="font-semibold">优势分析</span>
          </div>
          <p className="mt-2 text-sm text-gray-500">
            发现优势学科和掌握良好的知识点
          </p>
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-400">
            <Calendar className="h-3 w-3" />
            <span>上传考试记录后自动分析</span>
          </div>
        </div>
      </div>

      <div className="mb-6 rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Bell className="h-5 w-5 text-purple-500" />
          定时查缺补漏提醒
        </h2>
        <p className="mb-4 text-sm text-gray-500">
          设置周期性学习分析提醒，系统会在指定时间自动分析薄弱知识点并推送到对话中
        </p>
        <div className="flex flex-wrap gap-3">
          {(["off", "daily", "weekly"] as const).map((option) => (
            <button
              key={option}
              onClick={() => setReminder(option)}
              disabled={saving}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition ${
                freq === option
                  ? option === "off"
                    ? "border-gray-400 bg-gray-100 text-gray-700"
                    : "border-purple-500 bg-purple-50 text-purple-700"
                  : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              {saving && freq === option ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : option === "off" ? (
                <BellOff className="h-4 w-4" />
              ) : (
                <Bell className="h-4 w-4" />
              )}
              {option === "off" ? "关闭" : option === "daily" ? "每天" : "每周一 9:00"}
            </button>
          ))}
        </div>
        {statusMsg && (
          <p className="mt-3 text-sm text-gray-500">{statusMsg}</p>
        )}
      </div>

      <div className="rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold">使用指引</h2>
        <div className="space-y-3 text-sm text-gray-600">
          <div className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">1</span>
            <span>在对话中上传或描述考试/作业成绩，系统会自动提取知识点</span>
          </div>
          <div className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">2</span>
            <span>使用 <code className="rounded bg-gray-100 px-1">upload_exam</code> 工具记录每次考核</span>
          </div>
          <div className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">3</span>
            <span>使用 <code className="rounded bg-gray-100 px-1">study_dashboard</code> 查看学习趋势</span>
          </div>
          <div className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">4</span>
            <span>使用 <code className="rounded bg-gray-100 px-1">gap_analysis</code> 获取查缺补漏建议</span>
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-lg border bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
            <TrendingUp className="h-5 w-5 text-gray-500" />
            学习趋势
          </h2>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : !Array.isArray(subjects) || subjects.length === 0 ? (
            <p className="text-sm text-gray-400 italic">暂无学习记录。请在对话中使用 upload_exam 工具上传成绩。</p>
          ) : (
            <div className="space-y-3">
              {subjects.map((s) => {
                const pct = s.avg_accuracy != null ? Math.round(s.avg_accuracy * 100) : 0;
                const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-400";
                return (
                  <div key={s.subject}>
                    <div className="flex items-center justify-between text-sm">
                      <span>{s.subject}</span>
                      <span className="text-gray-500">{pct}% · {s.count}次</span>
                    </div>
                    <div className="mt-1 h-2 w-full rounded-full bg-gray-200">
                      <div className={`h-2 rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-lg border bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
            <AlertTriangle className="h-5 w-5 text-red-500" />
            薄弱知识点
          </h2>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : gapData && gapData.weak_points_ranked.length > 0 ? (
            <div>
              <div className="flex flex-wrap gap-2">
                {gapData.weak_points_ranked.slice(0, 10).map((wp) => {
                  const maxCount = gapData.weak_points_ranked[0]?.count || 1;
                  const size = 0.7 + (wp.count / maxCount) * 0.6;
                  return (
                    <span
                      key={wp.point}
                      className="inline-block rounded-full bg-red-50 px-3 py-1 text-sm text-red-700"
                      style={{ fontSize: `${size * 0.875}rem`, opacity: 0.6 + (wp.count / maxCount) * 0.4 }}
                    >
                      {wp.point} <span className="text-xs text-red-400">×{wp.count}</span>
                    </span>
                  );
                })}
              </div>
              {gapData.suggestion && (
                <div className="mt-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-700">
                  💡 {gapData.suggestion}
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-gray-400 italic">暂无薄弱知识点数据。</div>
          )}
        </div>
      </div>
    </div>
  );
}
