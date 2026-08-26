"use client";

import { useCallback, useEffect, useState } from "react";
import {
  NotebookPen,
  Loader2,
  Trash2,
  CheckCircle,
  XCircle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Target,
  Brain,
} from "lucide-react";

interface MistakeItem {
  id: string;
  subject: string;
  source_type: string;
  question: string;
  ai_answer: string;
  ai_explanation: string;
  knowledge_points: string[];
  mistake_reason: string;
  difficulty: string;
  mastery: number;
  review_count: number;
  status: string;
  created_at: number;
}

interface ProfileData {
  subject_mastery: Record<string, { accuracy: number; sample_count: number }>;
  weak_knowledge_points: { point: string; fail_count: number; avg_mastery: number }[];
  preferred_majors: { major_id: string; major_name: string; fit_score: number }[];
  profile_summary: string;
  confidence: number;
  stats: { records: number; mistakes: number; open_mistakes: number; reviews: number };
}

interface StatsData {
  total: number;
  by_subject: { subject: string; count: number; avg_mastery: number }[];
  by_status: Record<string, number>;
}

const USER_ID = "default";

export default function MistakeBookPage() {
  const [subject, setSubject] = useState("数学");
  const [sourceType, setSourceType] = useState<"mistake" | "paper" | "homework">("mistake");
  const [content, setContent] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  const [mistakes, setMistakes] = useState<MistakeItem[]>([]);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [applying, setApplying] = useState(false);

  const refresh = useCallback(async () => {
    const [mis, st, pf] = await Promise.all([
      fetch(`/api/v1/study/mistakes?user_id=${USER_ID}&limit=100`).then((r) => (r.ok ? r.json() : [])),
      fetch(`/api/v1/study/mistakes/stats?user_id=${USER_ID}`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/v1/study/profile?user_id=${USER_ID}`).then((r) => (r.ok ? r.json() : null)),
    ]).catch(() => [[], null, null]);
    setMistakes(mis as MistakeItem[]);
    setStats(st as StatsData | null);
    setProfile(pf as ProfileData | null);
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const analyze = async () => {
    if (!content.trim()) {
      setStatusMsg("请先输入错题/试卷/作业内容");
      return;
    }
    setAnalyzing(true);
    setStatusMsg("");
    try {
      const res = await fetch("/api/v1/study/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: USER_ID,
          subject,
          source_type: sourceType,
          content,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatusMsg(`分析失败: ${data.message || "未知错误"}`);
      } else {
        setStatusMsg(
          data.analysis_status === "ok"
            ? `✅ 已分析并存入错题本（#${data.mistake_id}），知识点：${data.knowledge_points.join("、") || "无"}`
            : "已保存原文，AI 分析暂不可用，可稍后在错题列表中补充答案"
        );
        setContent("");
        refresh();
      }
    } catch {
      setStatusMsg("网络错误，请重试");
    } finally {
      setAnalyzing(false);
    }
  };

  const review = async (id: string, performance: boolean) => {
    await fetch(`/api/v1/study/mistakes/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ performance }),
    });
    refresh();
  };

  const remove = async (id: string) => {
    await fetch(`/api/v1/study/mistakes/${id}`, { method: "DELETE" });
    refresh();
  };

  const applyToVolunteer = async () => {
    setApplying(true);
    setStatusMsg("");
    try {
      const res = await fetch(`/api/v1/study/profile/apply?user_id=${USER_ID}`, { method: "POST" });
      const data = await res.json();
      setStatusMsg(res.ok ? "✅ 学习画像已应用到升学推荐（学业匹配度已更新）" : `应用失败: ${data.message || "未知错误"}`);
    } catch {
      setStatusMsg("网络错误，请重试");
    } finally {
      setApplying(false);
    }
  };

  const toggle = (id: string) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  const masteryBar = (v: number) => (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
      <div
        className={`h-full rounded-full ${v >= 0.7 ? "bg-green-500" : v >= 0.4 ? "bg-amber-500" : "bg-red-500"}`}
        style={{ width: `${Math.round(v * 100)}%` }}
      />
    </div>
  );

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <NotebookPen className="h-6 w-6 text-indigo-500" />
          错题本
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          上传错题 / 试卷 / 作业 → AI 分析答案与知识点 → 整理进错题本 → 画像驱动升学推荐
        </p>
      </div>

      {/* 上传分析 */}
      <div className="mb-6 rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="h-5 w-5 text-indigo-500" />
          AI 分析并整理进错题本
        </h2>
        <div className="mb-3 flex flex-wrap gap-3">
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="科目"
            className="w-32 rounded-lg border border-gray-200 px-3 py-2 text-sm"
          />
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as typeof sourceType)}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
          >
            <option value="mistake">错题</option>
            <option value="paper">试卷</option>
            <option value="homework">作业</option>
          </select>
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={5}
          placeholder="粘贴题目或作业内容，例如：已知函数 f(x)=x²-2x，求其在 [0,3] 上的最大值…"
          className="w-full rounded-lg border border-gray-200 p-3 text-sm focus:border-indigo-400 focus:outline-none"
        />
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={analyze}
            disabled={analyzing}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {analyzing ? "分析中…" : "AI 分析"}
          </button>
          {statusMsg && <span className="text-sm text-gray-500">{statusMsg}</span>}
        </div>
      </div>

      {/* 画像 */}
      <div className="mb-6 rounded-lg border bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Brain className="h-5 w-5 text-purple-500" />
            学习者画像
            <span className="ml-2 rounded-full bg-purple-50 px-2 py-0.5 text-xs text-purple-600">
              置信度 {profile ? Math.round(profile.confidence * 100) : 0}%
            </span>
          </h2>
          <button
            onClick={applyToVolunteer}
            disabled={applying}
            className="flex items-center gap-2 rounded-lg border border-purple-500 px-3 py-1.5 text-sm text-purple-600 transition hover:bg-purple-50 disabled:opacity-50"
          >
            {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Target className="h-4 w-4" />}
            应用到升学推荐
          </button>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载画像…
          </div>
        ) : profile && Object.keys(profile.subject_mastery).length > 0 ? (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium text-gray-600">学科掌握度</p>
              <div className="space-y-2">
                {Object.entries(profile.subject_mastery)
                  .sort(([, a], [, b]) => b.accuracy - a.accuracy)
                  .map(([name, m]) => (
                    <div key={name} className="flex items-center gap-3">
                      <span className="w-10 text-sm text-gray-600">{name}</span>
                      <div className="flex-1">{masteryBar(m.accuracy)}</div>
                      <span className="w-12 text-right text-xs text-gray-500">{Math.round(m.accuracy * 100)}%</span>
                    </div>
                  ))}
              </div>
              {profile.weak_knowledge_points.length > 0 && (
                <div className="mt-4">
                  <p className="mb-2 text-sm font-medium text-gray-600">待巩固知识点</p>
                  <div className="flex flex-wrap gap-2">
                    {profile.weak_knowledge_points.slice(0, 8).map((w) => (
                      <span key={w.point} className="rounded-full bg-red-50 px-2 py-1 text-xs text-red-600">
                        {w.point} ×{w.fail_count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div>
              <p className="mb-2 text-sm font-medium text-gray-600">画像 → 适合专业倾向（升学）</p>
              {profile.preferred_majors.length > 0 ? (
                <div className="space-y-2">
                  {profile.preferred_majors.slice(0, 8).map((m) => (
                    <div key={m.major_id} className="flex items-center gap-3">
                      <span className="flex-1 text-sm text-gray-700">{m.major_name}</span>
                      <div className="w-24">{masteryBar(m.fit_score)}</div>
                      <span className="w-12 text-right text-xs text-gray-500">{Math.round(m.fit_score * 100)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400">上传错题或成绩后自动生成专业倾向</p>
              )}
              <p className="mt-3 rounded-lg bg-purple-50 p-3 text-xs leading-relaxed text-purple-700">
                {profile.profile_summary}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400">暂无学习数据，上传错题/成绩后自动生成画像</p>
        )}
      </div>

      {/* 错题列表 */}
      <div className="rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <NotebookPen className="h-5 w-5 text-gray-500" />
          错题列表
          {stats && (
            <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
              共 {stats.total} 条
            </span>
          )}
        </h2>
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : mistakes.length === 0 ? (
          <p className="text-sm text-gray-400">错题本是空的，上传一道错题开始吧。</p>
        ) : (
          <div className="space-y-3">
            {mistakes.map((m) => (
              <div key={m.id} className="rounded-lg border border-gray-100 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">{m.subject}</span>
                      <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                        {m.source_type === "mistake" ? "错题" : m.source_type === "paper" ? "试卷" : "作业"}
                      </span>
                      <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{m.difficulty}</span>
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          m.status === "mastered" ? "bg-green-50 text-green-600" : "bg-amber-50 text-amber-600"
                        }`}
                      >
                        {m.status === "mastered" ? "已掌握" : "待复习"}
                      </span>
                    </div>
                    <p className="text-sm text-gray-800">{m.question || "（无题目文本）"}</p>
                  </div>
                  <div className="w-24 shrink-0">
                    <div className="mb-1 text-right text-xs text-gray-500">
                      掌握度 {Math.round(m.mastery * 100)}%
                    </div>
                    {masteryBar(m.mastery)}
                  </div>
                </div>

                {m.knowledge_points.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.knowledge_points.map((kp) => (
                      <span key={kp} className="rounded-full bg-gray-50 px-2 py-0.5 text-xs text-gray-600">
                        {kp}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => review(m.id, true)}
                    className="flex items-center gap-1 rounded-lg border border-green-200 bg-green-50 px-2.5 py-1 text-xs text-green-600 transition hover:bg-green-100"
                  >
                    <CheckCircle className="h-3.5 w-3.5" /> 复习做对
                  </button>
                  <button
                    onClick={() => review(m.id, false)}
                    className="flex items-center gap-1 rounded-lg border border-red-200 bg-red-50 px-2.5 py-1 text-xs text-red-600 transition hover:bg-red-100"
                  >
                    <XCircle className="h-3.5 w-3.5" /> 仍不会
                  </button>
                  <button
                    onClick={() => toggle(m.id)}
                    className="flex items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1 text-xs text-gray-500 transition hover:bg-gray-50"
                  >
                    {expanded[m.id] ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    答案与解析
                  </button>
                  <button
                    onClick={() => remove(m.id)}
                    className="ml-auto flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:text-red-500"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> 删除
                  </button>
                </div>

                {expanded[m.id] && (
                  <div className="mt-3 space-y-2 rounded-lg bg-gray-50 p-3 text-sm">
                    <p>
                      <span className="font-medium text-gray-600">答案：</span>
                      <span className="text-gray-800">{m.ai_answer || "（待补充）"}</span>
                    </p>
                    {m.ai_explanation && (
                      <p>
                        <span className="font-medium text-gray-600">解析：</span>
                        <span className="whitespace-pre-line text-gray-800">{m.ai_explanation}</span>
                      </p>
                    )}
                    {m.mistake_reason && (
                      <p>
                        <span className="font-medium text-gray-600">错因：</span>
                        <span className="text-gray-800">{m.mistake_reason}</span>
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
