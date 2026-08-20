"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Search, BarChart3, GraduationCap, Building2, MessageSquare,
  TrendingUp, Sliders, RotateCcw, Save, Zap, Download,
  ListOrdered, Shield, Trash2, Plus, GripVertical, ChevronDown, ChevronUp, Sparkles, Compass,
} from "lucide-react";
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Filler,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import VolunteerChatDrawer from "@/components/volunteer/VolunteerChatDrawer";
import AdmissionCountdown from "@/components/volunteer/AdmissionCountdown";
import Modal from "@/components/common/Modal";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Filler);

type Weights = Record<string, number>;

const FACTOR_LABELS: Record<string, string> = {
  academic_fit: "学业匹配度",
  admission_prob: "录取概率",
  dorm_quality: "宿舍条件",
  city_vitality: "城市活力",
  cost_efficiency: "生活成本",
  employment: "就业前景",
  career_alignment: "职业契合度",
};

const FACTOR_COLORS: Record<string, string> = {
  academic_fit: "bg-blue-500",
  admission_prob: "bg-green-500",
  dorm_quality: "bg-yellow-500",
  city_vitality: "bg-purple-500",
  cost_efficiency: "bg-pink-500",
  employment: "bg-orange-500",
  career_alignment: "bg-teal-500",
};

const FACTOR_LABELS_SHORT: Record<string, string> = {
  academic_fit: "学业",
  admission_prob: "录取",
  dorm_quality: "宿舍",
  city_vitality: "城市",
  cost_efficiency: "成本",
  employment: "就业",
  career_alignment: "职业",
};

interface RecommendItem {
  college_id: string;
  college_name: string;
  college_level: string;
  college_province: string;
  college_city: string;
  total_score: number;
  detail_scores: Record<string, number>;
  explanations: Record<string, string>;
}

interface AdmissionHistoryItem {
  year: number;
  min_rank: number;
  min_score: number;
  batch: string | null;
}

interface SlotMajor {
  major_id: string;
  major_name: string;
  admission_prob: number;
  order: number;
  tag: string;
  years?: string;
  campus?: string;
  tuition?: number;
}

interface SlotItem {
  college_id: string;
  college_name: string;
  province_code?: string;
  group_code: string;
  group_name: string;
  group_prob: number;
  admission_prob?: number;
  tier: string;
  order: number;
  adjustable: boolean;
  reason: string;
  majors: SlotMajor[];
  bargain_score?: number;
  rank_source?: string;
}

interface PlanData {
  id: string;
  user_id: string;
  province: string;
  exam_category: string;
  rank: number;
  score?: number | null;
  province_rules: Record<string, unknown>;
  slots: SlotItem[];
  status: string;
  batch?: string;
  created_at: number;
  updated_at: number;
}

interface SavedPlanSummary {
  id: string;
  created_at: number;
  province: string;
  exam_category?: string;
  batch?: string;
  status: string;
  slots_count: number;
  groups: number;
  score?: number | null;
  rank?: number | null;
  deleted_at?: number;
  remaining_days?: number;
}

interface GroupRecItem {
  college: Record<string, unknown>;
  province_code?: string;
  group_code: string;
  group_prob: number;
  total_score: number;
  majors: SlotMajor[];
  detail_scores: Record<string, number>;
  bargain_score?: number;
  rank_source?: string;
}

function formatMajorMeta(mj: Partial<SlotMajor>): string {
  const parts: string[] = [];
  if (mj.years) parts.push(`${mj.years}年`);
  if (mj.campus) parts.push(mj.campus);
  if (mj.tuition) parts.push(`${mj.tuition}元/年`);
  return parts.join(" · ");
}

/** 志愿表命名：志愿表{月日时分}（紧凑式，如 志愿表06281626）。 */
function planLabel(createdAt: number): string {
  const d = new Date(createdAt * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `志愿表${pad(d.getMonth() + 1)}${pad(d.getDate())}${pad(d.getHours())}${pad(d.getMinutes())}`;
}

/** 完整时间：6月28日 16:26。 */
function planFullTime(createdAt: number): string {
  const d = new Date(createdAt * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 分数/排名显示：585分/位次14362（无分数时仅显示位次）。 */
function formatScoreRank(score?: number | null, rank?: number | null): string {
  const s = score ? `${score}分` : "";
  const r = rank ? `位次${rank}` : "";
  if (s && r) return `${s}/${r}`;
  return s || r || "";
}

const USER_ID = "default";

export default function VolunteerPage() {
  const [score, setScore] = useState("");
  const [rank, setRank] = useState("");
  const [province, setProvince] = useState("广东");
  const [examCategory, setExamCategory] = useState("物理");
  const [batch, setBatch] = useState("本科批");
  const [electiveSubjects, setElectiveSubjects] = useState<string[]>([]);
  const [bonusPoints, setBonusPoints] = useState("");
  const [gender, setGender] = useState("");
  const [medicalRestrictions, setMedicalRestrictions] = useState<string[]>([]);
  const [allRestrictions, setAllRestrictions] = useState<{code: string; description: string}[]>([]);
  const [showRestrictions, setShowRestrictions] = useState(false);
  const [level, setLevel] = useState("");
  const [loading, setLoading] = useState(false);
  const [weights, setWeights] = useState<Weights | null>(null);
  const [saving, setSaving] = useState(false);
  const [autoTuning, setAutoTuning] = useState(false);
  const [recommendMsg, setRecommendMsg] = useState("");
  const [weightMsg, setWeightMsg] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [chatContext, setChatContext] = useState<Record<string, unknown> | undefined>(undefined);
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planMsg, setPlanMsg] = useState("");
  const [diagnosis, setDiagnosis] = useState<Record<string, unknown> | null>(null);
  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [aiTuning, setAiTuning] = useState(false);
  const [aiAdvice, setAiAdvice] = useState<{ summary?: string; advice?: { order?: number; college_name?: string; action?: string; suggest_college?: string | null; reason?: string }[] } | null>(null);
  const [showAiAdvice, setShowAiAdvice] = useState(false);
  const [hollandOpen, setHollandOpen] = useState(false);
  const [hollandQuestions, setHollandQuestions] = useState<{code: string; text: string}[]>([]);
  const [hollandDisclaimer, setHollandDisclaimer] = useState("");
  const [hollandAnswers, setHollandAnswers] = useState<Record<number, number>>({});
  const [hollandResult, setHollandResult] = useState<{
    result?: { top3?: string; top3_labels?: string[]; scores?: Record<string, number> } | null;
    major_recommendations?: { major: string; match_count: number; riasec_codes: string }[];
  } | null>(null);
  const [hollandLoading, setHollandLoading] = useState(false);
  const [hollandMsg, setHollandMsg] = useState("");
  const [savedPlans, setSavedPlans] = useState<SavedPlanSummary[]>([]);
  const [trashPlans, setTrashPlans] = useState<SavedPlanSummary[]>([]);
  const [showSavedPlans, setShowSavedPlans] = useState(false);
  const [historyTab, setHistoryTab] = useState<"plans" | "trash">("plans");
  const [allCategories, setAllCategories] = useState<string[]>([]);
  const [majorCategories, setMajorCategories] = useState<string[]>([]);
  const [strategies, setStrategies] = useState<string[]>(["default"]);
  const [cityTier, setCityTier] = useState("");
  const [selectedRegions, setSelectedRegions] = useState<string[]>([]);
  const [allCities, setAllCities] = useState<{city: string; province: string; region: string}[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [convertedRank, setConvertedRank] = useState<number | null>(null);
  const [browseGroups, setBrowseGroups] = useState<GroupRecItem[]>([]);
  const [browseMode, setBrowseMode] = useState(false);
  const [checkedMajors, setCheckedMajors] = useState<Record<string, string[]>>({});
  const [scoreRange, setScoreRange] = useState<[number, number] | null>(null);
  const [showDist, setShowDist] = useState(false);
  const [artCategory, setArtCategory] = useState("美术与设计");
  const [artDirection, setArtDirection] = useState<string>("美术与设计");
  const [cultureScore, setCultureScore] = useState("");
  const [majorScore, setMajorScore] = useState("");
  const [artComposite, setArtComposite] = useState<number | null>(null);
  const [artRank, setArtRank] = useState<number | null>(null);
  const [artCategories, setArtCategories] = useState<{ code: string; name: string; formula: string; directions?: string[] }[]>([]);
  const dragItem = useRef<number | null>(null);
  const dragOverItem = useRef<number | null>(null);
  const rangeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetch(`/api/v1/volunteer/weights/${USER_ID}`)
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((data) => setWeights(data.weights))
      .catch(() => {});
    fetch("/api/v1/volunteer/medical-restrictions")
      .then((r) => r.ok ? r.json() : [])
      .then((data) => setAllRestrictions(data))
      .catch(() => {});
    fetch("/api/v1/volunteer/major-categories")
      .then((r) => r.ok ? r.json() : { categories: [] })
      .then((data) => setAllCategories(data.categories || []))
      .catch(() => {});
    fetch("/api/v1/volunteer/art-sports/categories")
      .then((r) => r.ok ? r.json() : { categories: [] })
      .then((data) => setArtCategories(data.categories || []))
      .catch(() => {});
    loadSavedPlans();
  }, []);

  useEffect(() => {
    const url = selectedRegions.length > 0
      ? `/api/v1/volunteer/cities?regions=${encodeURIComponent(selectedRegions.join(","))}`
      : "/api/v1/volunteer/cities";
    fetch(url)
      .then((r) => r.ok ? r.json() : { cities: [] })
      .then((data) => setAllCities(data.cities || []))
      .catch(() => {});
  }, [selectedRegions]);

  const convertScoreToRank = useCallback(async (s: string) => {
    if (!s || !examCategory) { setConvertedRank(null); return; }
    try {
      const res = await fetch("/api/v1/study/rank-convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          score: parseInt(s),
          from_year: 2025, to_year: 2025,
          exam_category: examCategory,
          province: province,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setConvertedRank(data.output_rank);
      }
    } catch { /* ignore */ }
  }, [examCategory, province]);

  const toggleCategory = (cat: string) => {
    setMajorCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const handleExamCategoryChange = (value: string) => {
    setExamCategory(value);
    setBatch(value === "艺体类" ? "艺体类本科批" : "本科批");
  };

  useEffect(() => {
    if (examCategory !== "艺体类" || !cultureScore || !majorScore) {
      setArtComposite(null);
      setArtRank(null);
      return;
    }
    let cancelled = false;
    fetch("/api/v1/volunteer/art-sports/composite-score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        art_category: artCategory,
        art_direction: artDirection,
        culture_score: parseInt(cultureScore),
        major_score: parseInt(majorScore),
        bonus_points: bonusPoints ? parseInt(bonusPoints) : 0,
      }),
    })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((data) => {
        if (cancelled) return;
        setArtComposite(data.score);
        setArtRank(data.rank ?? null);
      })
      .catch(() => { if (!cancelled) { setArtComposite(null); setArtRank(null); } });
    return () => { cancelled = true; };
  }, [examCategory, artCategory, artDirection, cultureScore, majorScore, bonusPoints]);

  // 艺体类别切换时重置方向为默认
  useEffect(() => {
    const cat = artCategories.find((c) => c.code === artCategory);
    const dirs = cat?.directions || [artCategory];
    setArtDirection((prev) => (dirs.includes(prev) ? prev : dirs[0]));
  }, [artCategory, artCategories]);

  const loadSavedPlans = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/volunteer/plan/list?user_id=" + USER_ID);
      if (res.ok) {
        const data = await res.json();
        const plans: PlanData[] = data.plans || [];
        setSavedPlans(plans.map((p) => ({
          id: p.id,
          created_at: p.created_at,
          province: p.province,
          exam_category: p.exam_category,
          batch: p.batch,
          status: p.status,
          slots_count: (p.slots || []).length,
          groups: (p.province_rules?.groups as number) || 0,
          score: p.score,
          rank: p.rank,
        })));
      }
    } catch { /* ignore */ }
  }, []);

  const loadTrash = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/volunteer/plan/trash?user_id=" + USER_ID);
      if (res.ok) {
        const data = await res.json();
        const plans: (PlanData & { remaining_days?: number })[] = data.plans || [];
        setTrashPlans(plans.map((p) => ({
          id: p.id,
          created_at: p.created_at,
          province: p.province,
          exam_category: p.exam_category,
          batch: p.batch,
          status: p.status,
          slots_count: (p.slots || []).length,
          groups: (p.province_rules?.groups as number) || 0,
          score: p.score,
          rank: p.rank,
          remaining_days: p.remaining_days,
        })));
      }
    } catch { /* ignore */ }
  }, []);

  const loadPlan = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${id}`);
      if (res.ok) { setPlan(await res.json()); setPlanMsg(""); setShowSavedPlans(false); }
    } catch { /* ignore */ }
  }, []);

  const deleteSavedPlan = useCallback(async (id: string) => {
    try {
      await fetch(`/api/v1/volunteer/plan/${id}`, { method: "DELETE" });
      loadSavedPlans();
      loadTrash();
    } catch { /* ignore */ }
  }, [loadSavedPlans, loadTrash]);

  const restoreSavedPlan = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${id}/restore`, { method: "POST" });
      if (res.ok) { loadSavedPlans(); loadTrash(); }
    } catch { /* ignore */ }
  }, [loadSavedPlans, loadTrash]);

  const purgeSavedPlan = useCallback(async (id: string) => {
    try {
      await fetch(`/api/v1/volunteer/plan/${id}/purge`, { method: "POST" });
      loadTrash();
    } catch { /* ignore */ }
  }, [loadTrash]);

  const savePlan = useCallback(async () => {
    if (!plan) return;
    setPlanMsg("");
    try {
      // 防呆：若与最近一次保存内容完全一致（含 rank），直接提示不另存
      const latest = savedPlans[0];
      if (latest && latest.slots_count === plan.slots.length && latest.rank === plan.rank) {
        const latestFull = await (async () => {
          try {
            const r = await fetch(`/api/v1/volunteer/plan/${latest.id}`);
            return r.ok ? await r.json() : null;
          } catch { return null; }
        })();
        if (latestFull && JSON.stringify(latestFull.slots) === JSON.stringify(plan.slots)) {
          setPlanMsg(`与志愿表${planLabel(latest.created_at)}完全相同，未保存`);
          return;
        }
      }
      const res = await fetch(`/api/v1/volunteer/plan/${plan.id}/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: USER_ID }),
      });
      if (res.ok) {
        const newPlan = await res.json();
        setPlan(newPlan);
        setPlanMsg("已保存为新方案");
        loadSavedPlans();
      } else if (res.status === 409) {
        const data = await res.json().catch(() => null);
        setPlanMsg(data?.detail || "当前方案与已有历史方案完全相同，未另存");
      } else {
        throw new Error("保存失败");
      }
    } catch (e) {
      setPlanMsg(e instanceof Error ? e.message : "保存失败");
    }
  }, [plan, savedPlans, loadSavedPlans]);

  const toggleCity = (city: string) => {
    setSelectedCities((prev) =>
      prev.includes(city) ? prev.filter((c) => c !== city) : [...prev, city]
    );
  };

  const toggleElective = (subject: string) => {
    setElectiveSubjects((prev) =>
      prev.includes(subject) ? prev.filter((s) => s !== subject) : [...prev, subject]
    );
  };

  const toggleRestriction = (code: string) => {
    setMedicalRestrictions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  };

  const updateWeight = useCallback((key: string, newValue: number) => {
    setWeights((prev) => {
      if (!prev) return prev;
      const others = Object.keys(prev).filter((k) => k !== key);
      const othersTotal = others.reduce((s, k) => s + prev[k], 0);
      if (othersTotal === 0) {
        const even = (1 - newValue) / others.length;
        const next = { ...prev, [key]: newValue };
        for (const k of others) next[k] = even;
        return next;
      }
      const scale = (1 - newValue) / othersTotal;
      const next: Weights = {};
      for (const k of others) next[k] = Math.round(prev[k] * scale * 100) / 100;
      next[key] = newValue;
      return next;
    });
  }, []);

  const saveWeights = useCallback(async () => {
    if (!weights) return;
    setSaving(true);
    setWeightMsg("");
    try {
      const res = await fetch(`/api/v1/volunteer/weights/${USER_ID}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: USER_ID, weights }),
      });
      if (!res.ok) {
        const err = await res.json();
        setWeightMsg(err.detail?.message || "保存失败");
        return;
      }
      const data = await res.json();
      setWeights(data.weights);
      setWeightMsg("权重已保存");
    } catch {
      setWeightMsg("网络错误");
    } finally {
      setSaving(false);
    }
  }, [weights]);

  const resetWeights = useCallback(async () => {
    setWeightMsg("");
    try {
      const res = await fetch(`/api/v1/volunteer/weights/${USER_ID}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("重置失败");
      const data = await res.json();
      setWeights(data.weights);
      setWeightMsg("已重置为默认权重");
    } catch {
      setWeightMsg("重置失败");
    }
  }, []);

  const autoTune = useCallback(async () => {
    setAutoTuning(true);
    setWeightMsg("");
    try {
      const res = await fetch(`/api/v1/volunteer/weights/auto-tune/${USER_ID}`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || "自动调优失败");
      }
      const data = await res.json();
      setWeights(data.weights);
      if (data.auto_tuned) {
        setWeightMsg("已根据学习记录自动调整权重");
      } else {
        setWeightMsg("学习数据不足，已恢复默认权重");
      }
    } catch (e) {
      setWeightMsg(e instanceof Error ? e.message : "自动调优失败");
    } finally {
      setAutoTuning(false);
    }
  }, []);

  const handleRecommend = useCallback(async (directScoreRange?: [number, number]) => {
    setLoading(true);
    setRecommendMsg("");
    setBrowseGroups([]);
    setBrowseMode(false);
    setPlan(null);
    setDiagnosis(null);
    setCheckedMajors({});
    const effectiveScoreRange = directScoreRange || scoreRange;
    try {
      const res = await fetch("/api/v1/volunteer/browse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          admission_province: province,
          exam_category: examCategory,
          user_rank: rank ? parseInt(rank) : null,
          score: score ? parseInt(score) : null,
          level: level || null,
          strategies: strategies.length > 0 ? strategies : ["default"],
          major_categories: majorCategories.length > 0 ? majorCategories : null,
          ...(cityTier ? { city_tier: cityTier } : {}),
          ...(selectedRegions.length > 0 ? { regions: selectedRegions } : {}),
          ...(selectedCities.length > 0 ? { cities: selectedCities } : {}),
          ...(effectiveScoreRange ? { score_min: effectiveScoreRange[0], score_max: effectiveScoreRange[1] } : {}),
          batch,
          ...(examCategory === "艺体类" ? {
            art_category: artCategory,
            culture_score: cultureScore ? parseInt(cultureScore) : null,
            major_score: majorScore ? parseInt(majorScore) : null,
          } : {}),
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `请求失败 (${res.status})`);
      }
      const data = await res.json();
      const allItems: GroupRecItem[] = [];
      for (const tierKey of ["reach", "steady", "safe"]) {
        const items = (data.tiers?.[tierKey] || []) as Record<string, unknown>[];
        for (const item of items) {
          allItems.push({
            college: {
              id: item.college_id,
              name: item.college_name,
              province: item.college_province,
            },
            province_code: item.province_code as string | undefined,
            group_code: item.group_code as string,
            group_prob: item.group_prob as number,
            total_score: item.total_score as number,
            majors: (item.majors || []) as GroupRecItem["majors"],
            detail_scores: (item.detail_scores || {}) as Record<string, number>,
            bargain_score: item.bargain_score as number | undefined,
            rank_source: item.rank_source as string | undefined,
          });
        }
      }
      if (allItems.length === 0) {
        if (examCategory === "艺体类" && data.data_status === "no_data") {
          setRecommendMsg("艺体类投档数据待补充，暂无可推荐院校专业组（框架已就绪）");
        } else {
          setRecommendMsg("未找到匹配的院校专业组，请调整筛选条件");
        }
        return;
      }
      setBrowseGroups(allItems);
      setBrowseMode(true);
      setRecommendMsg(`共找到 ${allItems.length} 个推荐专业组`);

      // Default: all majors checked
      const defaults: Record<string, string[]> = {};
      for (const g of allItems) {
        const key = `${(g.college as Record<string, string>).id}|${g.group_code}`;
        defaults[key] = (g.majors || []).map((m) => m.major_id);
      }
      setCheckedMajors(defaults);
    } catch (e) {
      setRecommendMsg(e instanceof Error ? e.message : "推荐请求失败");
    } finally {
      setLoading(false);
    }
  }, [province, examCategory, batch, rank, level, strategies, majorCategories, score, cityTier, selectedRegions, selectedCities, scoreRange, artCategory, cultureScore, majorScore]);

  const toggleMajor = useCallback((groupKey: string, majorId: string) => {
    setCheckedMajors((prev) => {
      const current = prev[groupKey] || [];
      const next = current.includes(majorId)
        ? current.filter((id) => id !== majorId)
        : [...current, majorId];
      return { ...prev, [groupKey]: next };
    });
  }, []);

  const addToPlan = useCallback(async (group: GroupRecItem, selectedMajorIds: string[]) => {
    const college = group.college as Record<string, string>;
    const filteredMajors = (group.majors || []).filter((m) => selectedMajorIds.includes(m.major_id));
    if (filteredMajors.length === 0) return;
    const newSlot: SlotItem = {
      college_id: college.id,
      college_name: college.name || "",
      province_code: group.province_code || "",
      group_code: group.group_code,
      group_name: `${group.group_code}组`,
      group_prob: group.group_prob,
      tier: group.group_prob >= 0.8 ? "safe" : group.group_prob >= 0.45 ? "steady" : "reach",
      order: (plan?.slots?.length || 0) + 1,
      adjustable: true,
      reason: `手动添加-${group.group_prob >= 0.8 ? "保底" : group.group_prob >= 0.45 ? "稳妥" : "冲刺"}`,
      majors: filteredMajors,
    };

    const savePlan = async (planId: string) => {
      try {
        const res = await fetch(`/api/v1/volunteer/plan/${planId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slots: [...(plan?.slots || []), newSlot] }),
        });
        if (res.ok) setPlan(await res.json());
      } catch { /* ignore */ }
    };

    if (plan) {
      await savePlan(plan.id);
    } else {
      try {
        const res = await fetch("/api/v1/volunteer/plan/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: USER_ID, province,
            exam_category: examCategory,
            rank: rank ? parseInt(rank) : 0,
            level: level || null,
            strategies: strategies.length > 0 ? strategies : ["default"],
            score: score ? parseInt(score) : null,
            batch,
...(examCategory === "艺体类" ? {
            art_category: artCategory,
            art_direction: artDirection,
            culture_score: cultureScore ? parseInt(cultureScore) : null,
            major_score: majorScore ? parseInt(majorScore) : null,
          } : {}),
          }),
        });
        if (res.ok) {
          const newPlan = await res.json();
          newPlan.slots = [newSlot];
          const updateRes = await fetch(`/api/v1/volunteer/plan/${newPlan.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slots: newPlan.slots }),
          });
          if (updateRes.ok) setPlan(await updateRes.json());
        }
      } catch { /* ignore */ }
    }
  }, [plan, province, examCategory, batch, rank, level, strategies, artCategory, cultureScore, majorScore, score]);

  const createFullPlan = useCallback(async () => {
    if (!rank) { setPlanMsg("请先输入位次"); return; }
    setPlanLoading(true);
    setPlanMsg("");
    setPlan(null);
    setDiagnosis(null);
    try {
      const res = await fetch("/api/v1/volunteer/plan/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: USER_ID, province,
          exam_category: examCategory,
          rank: parseInt(rank),
          level: level || null,
          strategies: strategies.length > 0 ? strategies : ["default"],
          major_categories: majorCategories.length > 0 ? majorCategories : null,
          ...(cityTier ? { city_tier: cityTier } : {}),
          ...(selectedRegions.length > 0 ? { regions: selectedRegions } : {}),
          ...(selectedCities.length > 0 ? { cities: selectedCities } : {}),
          score: score ? parseInt(score) : null,
          batch,
          ...(examCategory === "艺体类" ? {
            art_category: artCategory,
            art_direction: artDirection,
            culture_score: cultureScore ? parseInt(cultureScore) : null,
            major_score: majorScore ? parseInt(majorScore) : null,
          } : {}),
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "生成失败");
      setPlan(await res.json());
      setPlanMsg("志愿表已生成");
    } catch (e) {
      setPlanMsg(e instanceof Error ? e.message : "请求失败");
    }
    setPlanLoading(false);
  }, [province, examCategory, batch, rank, level, strategies, majorCategories, score, cityTier, selectedRegions, selectedCities, artCategory, artDirection, cultureScore, majorScore]);

  const handleRangeChange = useCallback((minScore: number, maxScore: number) => {
    setScoreRange([minScore, maxScore]);
    if (rangeTimer.current) clearTimeout(rangeTimer.current);
    rangeTimer.current = setTimeout(() => {
      handleRecommend([minScore, maxScore]);
    }, 600);
  }, [handleRecommend]);

  const handleResetRange = useCallback(() => {
    setScoreRange(null);
    setShowDist(false);
    handleRecommend();
  }, [handleRecommend]);

  const handleDragStart = useCallback((key: string) => {
    if (!plan) return;
    dragItem.current = plan.slots.findIndex(s => `${s.college_id}-${s.group_code}` === key);
  }, [plan]);

  const handleDragEnter = useCallback((key: string) => {
    if (!plan) return;
    dragOverItem.current = plan.slots.findIndex(s => `${s.college_id}-${s.group_code}` === key);
  }, [plan]);

  const handleDragEnd = useCallback(async () => {
    if (!plan || dragItem.current === null || dragOverItem.current === null) return;
    if (dragItem.current === dragOverItem.current) return;
    const slots = [...plan.slots];
    const dragged = slots.splice(dragItem.current, 1)[0];
    slots.splice(dragOverItem.current, 0, dragged);
    const reordered = slots.map((s, i) => ({ ...s, order: i + 1 }));
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${plan.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slots: reordered }),
      });
      if (res.ok) setPlan(await res.json());
    } catch { /* ignore */ }
    dragItem.current = null;
    dragOverItem.current = null;
  }, [plan]);

  const reorderPlan = useCallback(async () => {
    if (!plan) return;
    setPlanMsg("");
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${plan.id}/reorder`, { method: "PUT" });
      if (!res.ok) throw new Error("调序失败");
      const data = await res.json();
      setPlan(data.plan);
      setPlanMsg(data.message || "重排完成");
    } catch (e) {
      setPlanMsg(e instanceof Error ? e.message : "请求失败");
    }
  }, [plan]);

  const diagnosePlan = useCallback(async () => {
    if (!plan) return;
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${plan.id}/diagnose`);
      if (!res.ok) throw new Error("诊断失败");
      setDiagnosis(await res.json());
      setShowDiagnosis(true);
    } catch (e) {
      setPlanMsg(e instanceof Error ? e.message : "请求失败");
    }
  }, [plan]);

  const deletePlan = useCallback(async () => {
    if (!plan) return;
    setPlanMsg("");
    try {
      await fetch(`/api/v1/volunteer/plan/${plan.id}`, { method: "DELETE" });
      setPlan(null);
      setDiagnosis(null);
      setPlanMsg("志愿表已删除");
    } catch (e) {
      setPlanMsg(e instanceof Error ? e.message : "请求失败");
    }
  }, [plan]);

  const aiTunePlan = useCallback(async () => {
    if (!plan) return;
    setPlanMsg("");
    setAiTuning(true);
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${plan.id}/ai-tune`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "AI 优化建议失败");
      }
      const data = await res.json();
      setAiAdvice(data);
      setShowAiAdvice(true);
      setPlanMsg(data.message || "AI 优化建议已生成");
    } catch (e) {
      setPlanMsg(e instanceof Error ? e.message : "请求失败");
    } finally {
      setAiTuning(false);
    }
  }, [plan]);

  const loadHolland = useCallback(async () => {
    setHollandLoading(true);
    setHollandMsg("");
    try {
      const [qRes, rRes] = await Promise.all([
        fetch("/api/v1/volunteer/holland/questions"),
        fetch(`/api/v1/volunteer/holland/result/${USER_ID}`),
      ]);
      const qData = await qRes.json();
      setHollandQuestions(qData.questions || []);
      setHollandDisclaimer(qData.disclaimer || "");
      const rData = await rRes.json();
      if (rData.result) {
        setHollandResult(rData);
      }
    } catch {
      setHollandMsg("测评加载失败");
    } finally {
      setHollandLoading(false);
    }
  }, []);

  const submitHolland = useCallback(async () => {
    const total = Object.values(hollandAnswers);
    if (total.length < hollandQuestions.length) {
      setHollandMsg("请完成所有题目后再提交");
      return;
    }
    setHollandLoading(true);
    setHollandMsg("");
    const scores: Record<string, number> = {};
    for (let i = 0; i < hollandQuestions.length; i++) {
      const code = hollandQuestions[i].code;
      scores[code] = (scores[code] || 0) + hollandAnswers[i];
    }
    try {
      const res = await fetch("/api/v1/volunteer/holland/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: USER_ID, scores }),
      });
      if (!res.ok) throw new Error("提交失败");
      setHollandResult(await res.json());
    } catch (e) {
      setHollandMsg(e instanceof Error ? e.message : "请求失败");
    } finally {
      setHollandLoading(false);
    }
  }, [hollandAnswers, hollandQuestions]);

  const resetHolland = useCallback(() => {
    setHollandAnswers({});
    setHollandResult(null);
  }, []);

  const deleteSlot = useCallback(async (idx: number) => {
    if (!plan) return;
    const updated = plan.slots.filter((_, i) => i !== idx).map((s, i) => ({ ...s, order: i + 1 }));
    try {
      const res = await fetch(`/api/v1/volunteer/plan/${plan.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slots: updated }),
      });
      if (res.ok) setPlan(await res.json());
    } catch { /* ignore */ }
  }, [plan]);

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <GraduationCap className="h-6 w-6 text-blue-500" />
          志愿填报助手
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          基于多因子模型的智能志愿推荐系统
        </p>
      </div>

      <div className="mb-8 rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold">考生信息</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">考生省份</label>
            <select
              value={province}
              onChange={(e) => setProvince(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="广东">广东</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">选考科目</label>
            <div className="mt-1 flex gap-3">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="examCategory"
                  value="物理"
                  checked={examCategory === "物理"}
                  onChange={(e) => handleExamCategoryChange(e.target.value)}
                  className="accent-blue-600"
                />
                <span className="text-sm">物理类</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="examCategory"
                  value="历史"
                  checked={examCategory === "历史"}
                  onChange={(e) => handleExamCategoryChange(e.target.value)}
                  className="accent-blue-600"
                />
                <span className="text-sm">历史类</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="examCategory"
                  value="艺体类"
                  checked={examCategory === "艺体类"}
                  onChange={(e) => handleExamCategoryChange(e.target.value)}
                  className="accent-purple-600"
                />
                <span className="text-sm text-purple-700">艺体类</span>
              </label>
            </div>
          </div>
          {examCategory === "艺体类" && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700">专业类别</label>
                <select
                  value={artCategory}
                  onChange={(e) => setArtCategory(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-purple-500 focus:outline-none"
                >
                  {artCategories.length > 0
                    ? artCategories.map((c) => (
                        <option key={c.code} value={c.code}>{c.name}</option>
                      ))
                    : (
                        ["音乐", "舞蹈", "表（导）演", "播音与主持", "美术与设计", "书法", "戏曲", "体育"].map((c) => (
                          <option key={c} value={c}>{c === "美术与设计" ? "美术与设计类" : c === "播音与主持" ? "播音与主持类" : c === "表（导）演" ? "表（导）演类" : `${c}类`}</option>
                        ))
                    )}
                </select>
                <p className="mt-1 text-xs text-purple-600">
                  艺体类不分物理/历史，按专业类别统一划线、一起投档
                </p>
              </div>
              {(() => {
                const cat = artCategories.find((c) => c.code === artCategory);
                const dirs = cat?.directions?.length ? cat.directions : [artCategory];
                if (dirs.length <= 1) return null;
                return (
                  <div>
                    <label className="block text-sm font-medium text-gray-700">方向细分</label>
                    <select
                      value={artDirection}
                      onChange={(e) => setArtDirection(e.target.value)}
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-purple-500 focus:outline-none"
                    >
                      {dirs.map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                    <p className="mt-1 text-xs text-gray-500">
                      方向不同，同一综合分对应的位次不同（按方向一分一段表换算）
                    </p>
                  </div>
                );
              })()}
              <div>
                <label className="block text-sm font-medium text-gray-700">文化课分数</label>
                <input
                  type="number"
                  value={cultureScore}
                  onChange={(e) => setCultureScore(e.target.value)}
                  placeholder="0-750"
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-purple-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">专业省统考分</label>
                <input
                  type="number"
                  value={majorScore}
                  onChange={(e) => setMajorScore(e.target.value)}
                  placeholder="0-300"
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-purple-500 focus:outline-none"
                />
                {artComposite !== null && (
                  <p className="mt-1 text-sm font-medium text-purple-700">
                    综合分 ≈ {artComposite.toFixed(1)}
                    {artRank ? ` · 位次 ≈ ${artRank}` : ""}
                  </p>
                )}
                <p className="mt-1 text-xs text-gray-500">
                  双上线：文化与专业省统考须同时达省控线方可投档
                </p>
              </div>
            </>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700">招生批次</label>
            <select
              value={batch}
              onChange={(e) => setBatch(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="本科批">本科批（普通类）</option>
              {examCategory === "艺体类" && (
                <option value="艺体类本科批">本科批（艺体类）</option>
              )}
              <option value="提前批本科-军检类">提前批·军检类</option>
              <option value="提前批本科-非军检类">提前批·非军检类</option>
              <option value="提前批本科-卫生专项">提前批·卫生专项</option>
              <option value="提前批本科-教师专项">提前批·教师专项</option>
              <option value="提前批本科-特殊类型招生">提前批·特殊类型招生</option>
              <option value="提前批本科-空军海军招飞">提前批·空军海军招飞</option>
            </select>
            {batch === "艺体类本科批" && (
              <p className="mt-1 text-xs text-purple-600">
                艺体类本科批：1 个平行志愿组共 20 个院校专业组 · 每组最多 6 个专业 · 不得兼报普通类
              </p>
            )}
            {batch !== "本科批" && batch !== "艺体类本科批" && (
              <p className="mt-1 text-xs text-amber-600">
                提前批：军检/卫生/教师等专项有特定报考条件与就业限制，请仔细核对招生章程
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">再选科目</label>
            <div className="mt-1 flex flex-wrap gap-2">
              {examCategory === "艺体类" ? (
                <span className="text-xs text-gray-400">艺体类不分物理/历史，无再选科目要求</span>
              ) : (["化学", "生物", "地理", "政治"].map((subj) => (
                <label key={subj} className="flex items-center gap-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={electiveSubjects.includes(subj)}
                    onChange={() => toggleElective(subj)}
                    className="accent-blue-600"
                  />
                  <span className="text-sm">{subj}</span>
                </label>
              )))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">性别</label>
            <div className="mt-1 flex gap-3">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="gender"
                  value="男"
                  checked={gender === "男"}
                  onChange={(e) => setGender(e.target.value)}
                  className="accent-blue-600"
                />
                <span className="text-sm">男</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="gender"
                  value="女"
                  checked={gender === "女"}
                  onChange={(e) => setGender(e.target.value)}
                  className="accent-blue-600"
                />
                <span className="text-sm">女</span>
              </label>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">预估分数</label>
            <input
              type="number"
              value={score}
              onChange={(e) => { setScore(e.target.value); convertScoreToRank(e.target.value); }}
              placeholder="例如: 620"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-700">预估位次</label>
              {convertedRank && (
                <span className="text-xs text-green-600">≈ 约 {convertedRank.toLocaleString()} 名</span>
              )}
              <button
                onClick={() => { setChatOpen(true); setChatContext(undefined); }}
                className="flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-100 transition-colors"
                title="咨询 AI 志愿顾问"
              >
                <MessageSquare className="h-3.5 w-3.5" />
                问 AI
              </button>
            </div>
            <input
              type="number"
              value={rank}
              onChange={(e) => setRank(e.target.value)}
              placeholder="例如: 5000"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">政策性加分</label>
            <input
              type="number"
              value={bonusPoints}
              onChange={(e) => setBonusPoints(e.target.value)}
              placeholder="0"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">院校层次</label>
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">全部层次</option>
              <option value="985">985</option>
              <option value="211">211</option>
              <option value="双一流">双一流</option>
              <option value="普通">普通</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">城市等级</label>
            <select
              value={cityTier}
              onChange={(e) => setCityTier(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">不限</option>
              <option value="一线">一线</option>
              <option value="新一线">新一线</option>
              <option value="二线">二线</option>
              <option value="三线">三线</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">推荐策略</label>
            <div className="mt-1 flex flex-wrap gap-2">
              {[{v:"default",l:"综合"},{v:"admission_only",l:"录取概率"},{v:"major_first",l:"专业优先"},{v:"city_first",l:"城市优先"}].map((opt) => (
                <label key={opt.v} className="flex items-center gap-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={strategies.includes(opt.v)}
                    onChange={() => setStrategies(prev => prev.includes(opt.v) ? prev.filter(s => s !== opt.v) : [...prev, opt.v])}
                    className="accent-blue-600"
                  />
                  <span className="text-sm">{opt.l}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">地域大区</label>
            <div className="mt-1 flex flex-wrap gap-2">
              {["华北","东北","华东","华中","华南","西南","西北","港澳台"].map((r) => (
                <label key={r} className="flex items-center gap-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedRegions.includes(r)}
                    onChange={() => setSelectedRegions(prev =>
                      prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]
                    )}
                    className="accent-blue-600"
                  />
                  <span className="text-sm">{r}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">学科门类</label>
            <div className="mt-1 max-h-32 overflow-y-auto rounded-md border border-gray-200 p-2">
              {allCategories.length === 0 && (
                <span className="text-xs text-gray-400">加载中...</span>
              )}
              <div className="flex flex-wrap gap-1.5">
                {allCategories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => toggleCategory(cat)}
                    className={`rounded px-2 py-0.5 text-xs border ${
                      majorCategories.includes(cat)
                        ? "bg-blue-100 border-blue-300 text-blue-700"
                        : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
              {allCategories.length > 0 && majorCategories.length > 0 && (
                <button
                  type="button"
                  onClick={() => setMajorCategories([])}
                  className="mt-1 text-xs text-gray-400 hover:text-gray-600"
                >
                  清除筛选
                </button>
              )}
            </div>
          </div>
          <div className="md:col-span-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">城市</label>
            <div className="max-h-40 overflow-y-auto rounded-md border border-gray-200 p-2">
              {allCities.length === 0 && (
                <span className="text-xs text-gray-400">加载中...</span>
              )}
              {(() => {
                const grouped: Record<string, {city:string;province:string}[]> = {};
                for (const c of allCities) {
                  const grp = c.region || "其他";
                  if (!grouped[grp]) grouped[grp] = [];
                  grouped[grp].push(c);
                }
                return Object.entries(grouped).map(([grp, cities]) => (
                  <div key={grp} className="mb-2">
                    <div className="mb-1 text-xs font-medium text-gray-500">{grp}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {cities.map((c) => (
                        <button
                          key={c.city}
                          type="button"
                          onClick={() => toggleCity(c.city)}
                          className={`rounded px-2 py-0.5 text-xs border ${
                            selectedCities.includes(c.city)
                              ? "bg-blue-100 border-blue-300 text-blue-700"
                              : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
                          }`}
                        >
                          {c.city.replace("市", "")}
                        </button>
                      ))}
                    </div>
                  </div>
                ));
              })()}
              {selectedCities.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedCities([])}
                  className="mt-1 text-xs text-gray-400 hover:text-gray-600"
                >
                  清除筛选
                </button>
              )}
            </div>
          </div>
        </div>
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700">体检受限项</label>
          <button
            type="button"
            onClick={() => setShowRestrictions(!showRestrictions)}
            className="mt-1 inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            {medicalRestrictions.length === 0
              ? "选择体检受限项（如有）"
              : `已选 ${medicalRestrictions.length} 项`}
          </button>
          {showRestrictions && (
            <div className="mt-2 max-h-48 overflow-y-auto rounded-md border bg-white p-3">
              {allRestrictions.map((r) => (
                <label key={r.code} className="flex items-start gap-2 py-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={medicalRestrictions.includes(r.code)}
                    onChange={() => toggleRestriction(r.code)}
                    className="mt-0.5 accent-blue-600"
                  />
                  <span className="text-sm text-gray-700">
                    [{r.code}] {r.description}
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>
        {recommendMsg && (
          <p className="mt-2 text-sm text-red-600">{recommendMsg}</p>
        )}
        {/* 分数分布面板 */}
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowDist(!showDist)}
            className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
          >
            {showDist ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            分数分布 {showDist ? "收起" : "展开"}
          </button>
          {showDist && (
            <ScoreDistributionChart
              province={province}
              examCategory={examCategory}
              currentScore={score ? parseInt(score) : null}
              onRangeChange={handleRangeChange}
              onReset={handleResetRange}
            />
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => handleRecommend()}
            disabled={loading || !rank}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
            {loading ? "查询中..." : "查询推荐"}
          </button>
          <button
            onClick={createFullPlan}
            disabled={planLoading || !rank}
            className="inline-flex items-center gap-2 rounded-md border border-blue-200 bg-white px-4 py-2 text-blue-600 hover:bg-blue-50 disabled:opacity-50"
          >
            <ListOrdered className="h-4 w-4" />
            {planLoading ? "生成中..." : "一键生成45格"}
          </button>
          <button
            onClick={() => { setChatOpen(true); setChatContext(undefined); }}
            type="button"
            className="inline-flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-blue-600 hover:bg-blue-100 transition-colors"
          >
            <MessageSquare className="h-4 w-4" />
            问 AI
          </button>
          <button
            onClick={() => {
              loadSavedPlans();
              loadTrash();
              setHistoryTab("plans");
              setShowSavedPlans(v => !v);
            }}
            type="button"
            className="inline-flex items-center gap-2 rounded-md border border-gray-200 bg-white px-4 py-2 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <ListOrdered className="h-4 w-4" />
            历史方案
          </button>
        </div>
      </div>

      {/* 浏览推荐 */}
      {browseMode && browseGroups.length > 0 && (
        <div className="mb-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">浏览推荐 — {browseGroups.length} 个专业组</h2>
            <button
              onClick={() => setBrowseMode(false)}
              className="text-sm text-gray-400 hover:text-gray-600"
            >
              收起
            </button>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {(["reach", "steady", "safe"] as const).map((tier) => {
              const tierGroups = browseGroups.filter(g =>
                tier === "reach" ? g.group_prob < 0.45
                : tier === "steady" ? g.group_prob >= 0.45 && g.group_prob < 0.8
                : g.group_prob >= 0.8
              );
              const labels = { reach: { title: "冲刺志愿", icon: <TrendingUp className="h-5 w-5" />, color: "text-green-600", desc: "录取概率 < 45%", max: 50 }, steady: { title: "稳妥志愿", icon: <BarChart3 className="h-5 w-5" />, color: "text-yellow-600", desc: "录取概率 45%-80%", max: 100 }, safe: { title: "保底志愿", icon: <Building2 className="h-5 w-5" />, color: "text-blue-600", desc: "录取概率 ≥ 80%", max: 80 } };
              const l = labels[tier];
              return (
                <div key={tier} className="rounded-lg border bg-white p-4 shadow-sm">
                  <div className={`flex items-center gap-2 ${l.color}`}>
                    {l.icon}
                    <h3 className="font-semibold">{l.title}</h3>
                    <span className="ml-auto text-sm text-gray-400">{tierGroups.length}/{l.max}</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-400">{l.desc}</p>
                  <div className="mt-3 max-h-96 space-y-3 overflow-y-auto">
                    {tierGroups.length === 0 && (
                      <div className="rounded bg-gray-50 p-3 text-sm text-gray-400 italic">暂无</div>
                    )}
                    {tierGroups.map((g, i) => {
                      const c = g.college as Record<string, string>;
                      const key = `${c.id}|${g.group_code}`;
                      const checked = checkedMajors[key] || [];
                      const alreadyAdded = plan?.slots?.some(s => s.college_id === c.id && s.group_code === g.group_code);
                      const allIds = (g.majors || []).map((mj) => mj.major_id);
                      const allChecked = allIds.length > 0 && allIds.every((id) => checked.includes(id));
                      return (
                        <div key={key} className="rounded-lg border bg-white p-3 shadow-sm">
                          <div className="flex items-start justify-between">
                            <div className="min-w-0">
                              <span className="text-sm font-medium text-gray-900">{c.name}</span>
                              {g.province_code && (
                                <span className="ml-1.5 rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">代码 {g.province_code}</span>
                              )}
                              <span className="ml-1.5 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">{g.group_code}组</span>
                              {g.rank_source === "estimated" && (
                                <span className="ml-1 rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-600" title="该专业组无官方投档位次，位次为预估">预估位次</span>
                              )}
                              {(g.bargain_score ?? 0) >= 0.6 && (
                                <span className="ml-1 rounded bg-orange-100 px-1.5 py-0.5 text-xs text-orange-600">捡漏</span>
                              )}
                            </div>
                            <span className="whitespace-nowrap text-sm font-bold text-blue-600">{Math.round(g.group_prob * 100)}%</span>
                          </div>
                          <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200">
                            <div className={`h-1.5 rounded-full ${g.group_prob >= 0.8 ? "bg-green-500" : g.group_prob >= 0.45 ? "bg-yellow-500" : "bg-red-400"}`}
                              style={{ width: `${Math.round(g.group_prob * 100)}%` }} />
                          </div>

                          {/* 组内专业列表 */}
                          {g.majors && g.majors.length > 0 ? (
                            <div className="mt-2 space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="text-xs text-gray-400">组内专业</span>
                                <label className="flex items-center gap-1 text-xs text-gray-500 cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={allChecked}
                                    onChange={() => {
                                      if (allChecked) setCheckedMajors((prev) => ({ ...prev, [key]: [] }));
                                      else setCheckedMajors((prev) => ({ ...prev, [key]: [...allIds] }));
                                    }}
                                    className="accent-blue-600"
                                  />
                                  全选
                                </label>
                              </div>
                              {(g.majors || []).map((mj) => {
                                const prob = mj.admission_prob ?? g.group_prob;
                                const tagColor = mj.tag === "推荐" ? "bg-green-100 text-green-700"
                                  : mj.tag === "优选" ? "bg-yellow-100 text-yellow-700"
                                  : "bg-gray-100 text-gray-500";
                                return (
                                  <label key={mj.major_id} className="flex items-center gap-2 rounded bg-gray-50 px-2 py-1.5 cursor-pointer hover:bg-gray-100">
                                    <input
                                      type="checkbox"
                                      checked={checked.includes(mj.major_id)}
                                      onChange={() => toggleMajor(key, mj.major_id)}
                                      className="shrink-0 accent-blue-600"
                                    />
                                    <span className="min-w-0 flex-1">
                                      <span className="block truncate text-xs text-gray-700">{mj.major_name}</span>
                                      <span className="block truncate text-[10px] text-gray-400">{formatMajorMeta(mj) || "\u00a0"}</span>
                                    </span>
                                    {mj.tag && (
                                      <span className={`shrink-0 rounded px-1 py-0.5 text-xs ${tagColor}`}>{mj.tag}</span>
                                    )}
                                    <div className="flex shrink-0 items-center gap-1.5">
                                      <div className="h-1.5 w-12 rounded-full bg-gray-200">
                                        <div className={`h-1.5 rounded-full ${prob >= 0.8 ? "bg-green-500" : prob >= 0.45 ? "bg-yellow-500" : "bg-red-400"}`}
                                          style={{ width: `${Math.round(prob * 100)}%` }} />
                                      </div>
                                      <span className="w-7 text-right text-xs text-gray-400">{Math.round(prob * 100)}%</span>
                                    </div>
                                  </label>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="mt-2 text-xs text-gray-400 italic">无细分专业</div>
                          )}

                          <button
                            onClick={() => addToPlan(g, checked)}
                            disabled={alreadyAdded || checked.length === 0}
                            className="mt-2 inline-flex w-full items-center justify-center gap-1 rounded-md border border-blue-200 px-2.5 py-1.5 text-xs text-blue-600 hover:bg-blue-50 disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
                          >
                            <Plus className="h-3 w-3" />
                            {alreadyAdded ? "已加入" : checked.length === 0 ? "请勾选专业" : `加入志愿表 (${checked.length}个专业)`}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 当前志愿表 */}
      {plan && plan.slots.length > 0 && (
        <div className="mb-8">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              <span className="mr-2">当前志愿表</span>
              <span className="mr-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-600">{planLabel(plan.created_at)}</span>
              <span className="mr-2 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-600">
                {formatScoreRank(plan.score, plan.rank) || "—"}
              </span>
              <span className="text-sm font-normal text-gray-500">({plan.slots.length} 个)</span>
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <PlanTierCard
              title="冲刺志愿"
              icon={<TrendingUp className="h-5 w-5" />}
              color="text-green-600"
              desc="录取概率较低的院校专业组"
              items={plan.slots.filter(s => s.tier === "reach")}
              onDragStart={handleDragStart}
              onDragEnter={handleDragEnter}
              onDragEnd={handleDragEnd}
              onChat={(item) => {
                setChatContext({ college_name: item.college_name, college_id: item.college_id, tier: "冲刺", province, exam_category: examCategory, rank: rank || undefined });
                setChatOpen(true);
              }}
              onDelete={deleteSlot}
            />
            <PlanTierCard
              title="稳妥志愿"
              icon={<BarChart3 className="h-5 w-5" />}
              color="text-yellow-600"
              desc="与考生水平匹配的院校专业组"
              items={plan.slots.filter(s => s.tier === "steady")}
              onDragStart={handleDragStart}
              onDragEnter={handleDragEnter}
              onDragEnd={handleDragEnd}
              onChat={(item) => {
                setChatContext({ college_name: item.college_name, college_id: item.college_id, tier: "稳妥", province, exam_category: examCategory, rank: rank || undefined });
                setChatOpen(true);
              }}
              onDelete={deleteSlot}
            />
            <PlanTierCard
              title="保底志愿"
              icon={<Building2 className="h-5 w-5" />}
              color="text-blue-600"
              desc="录取概率较高的院校专业组"
              items={plan.slots.filter(s => s.tier === "safe")}
              onDragStart={handleDragStart}
              onDragEnter={handleDragEnter}
              onDragEnd={handleDragEnd}
              onChat={(item) => {
                setChatContext({ college_name: item.college_name, college_id: item.college_id, tier: "保底", province, exam_category: examCategory, rank: rank || undefined });
                setChatOpen(true);
              }}
              onDelete={deleteSlot}
            />
          </div>
          {planMsg && <p className="mt-2 text-center text-sm text-blue-600">{planMsg}</p>}
          <div className="mt-4 flex flex-wrap justify-center gap-3">
            <button onClick={aiTunePlan} disabled={aiTuning} className="flex items-center gap-1.5 rounded-lg border bg-gradient-to-r from-violet-500 to-purple-500 px-4 py-2 text-sm font-medium text-white hover:from-violet-600 hover:to-purple-600 disabled:opacity-60">
              <Sparkles className="h-4 w-4" /> {aiTuning ? "AI 分析中…" : "AI 优化建议"}
            </button>
            <button onClick={savePlan} className="flex items-center gap-1.5 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50">
              <Save className="h-4 w-4" /> 保存
            </button>
            <button onClick={reorderPlan} className="flex items-center gap-1.5 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <ListOrdered className="h-4 w-4" /> 一键调序
            </button>
            <button onClick={diagnosePlan} className="flex items-center gap-1.5 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <Shield className="h-4 w-4" /> 诊断
            </button>
            <button onClick={deletePlan} className="flex items-center gap-1.5 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50">
              <Trash2 className="h-4 w-4" /> 清空
            </button>
            <a href={`/api/v1/volunteer/plan/${plan.id}/export-pdf`} download className="flex items-center gap-1.5 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <Download className="h-4 w-4" /> PDF
            </a>
            <a href={`/api/v1/volunteer/plan/${plan.id}/export-excel`} download className="flex items-center gap-1.5 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <Download className="h-4 w-4" /> Excel
            </a>
          </div>

          {/* Diagnosis panel */}
          {showDiagnosis && diagnosis && (
            <div className="mt-4 rounded-lg border bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">志愿表诊断</h3>
                <button onClick={() => setShowDiagnosis(false)} className="text-sm text-gray-400 hover:text-gray-600">关闭</button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-4">
                <div><span className="text-sm text-gray-500">梯度评分</span><p className="text-2xl font-bold">{diagnosis.grade_score as number || 0}/100</p></div>
                <div>
                  <span className="text-sm text-gray-500">滑档风险</span>
                  <p className={`text-2xl font-bold ${diagnosis.risk_level === "低" ? "text-green-600" : diagnosis.risk_level === "中" ? "text-yellow-600" : "text-red-600"}`}>
                    {diagnosis.risk_level as string}
                  </p>
                </div>
                <div><span className="text-sm text-gray-500">保底概率</span><p className="text-2xl font-bold">{Math.round((diagnosis.weakest_link_prob as number || 0) * 100)}%</p></div>
                <div><span className="text-sm text-gray-500">保底志愿</span><p className="text-2xl font-bold">{diagnosis.safe_slots_remaining as number || 0} 所</p></div>
              </div>
            </div>
          )}

          {/* AI 优化建议 */}
          {showAiAdvice && aiAdvice && (
            <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50/50 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 font-semibold text-violet-800">
                  <Sparkles className="h-4 w-4" /> AI 优化建议
                </h3>
                <button onClick={() => setShowAiAdvice(false)} className="text-sm text-gray-400 hover:text-gray-600">关闭</button>
              </div>
              {aiAdvice.summary && (
                <p className="mt-3 rounded-md border border-violet-200 bg-white p-3 text-sm leading-relaxed text-gray-700">{aiAdvice.summary}</p>
              )}
              <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">
                {(aiAdvice.advice || []).map((a, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-md border bg-white p-3 text-sm">
                    <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${a.action === "swap" ? "bg-amber-100 text-amber-700" : "bg-green-100 text-green-700"}`}>
                      {a.action === "swap" ? "建议替换" : "保留"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-gray-800">
                        #{a.order} {a.college_name}
                      </p>
                      {a.suggest_college && (
                        <p className="mt-0.5 text-xs text-amber-600">→ {a.suggest_college}</p>
                      )}
                      {a.reason && <p className="mt-1 text-xs leading-relaxed text-gray-500">{a.reason}</p>}
                    </div>
                  </div>
                ))}
                {(aiAdvice.advice || []).length === 0 && <p className="text-sm text-gray-400">暂无逐条建议</p>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 历史方案弹窗（志愿表 / 回收站） */}
      <Modal
        isOpen={showSavedPlans}
        onClose={() => setShowSavedPlans(false)}
        title="历史志愿方案"
        titleIcon={<ListOrdered className="h-5 w-5 text-blue-600" />}
        width="lg"
      >
        <div className="p-4">
          {/* Tab 切换 */}
          <div className="mb-4 flex items-center gap-1 rounded-lg bg-gray-100 p-1">
            <button
              type="button"
              onClick={() => { setHistoryTab("plans"); loadSavedPlans(); }}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${historyTab === "plans" ? "bg-white text-blue-600 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              志愿表（{savedPlans.length}）
            </button>
            <button
              type="button"
              onClick={() => { setHistoryTab("trash"); loadTrash(); }}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${historyTab === "trash" ? "bg-white text-blue-600 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
            >
              回收站（{trashPlans.length}）
            </button>
          </div>

          {historyTab === "plans" && (
            <div className="space-y-2">
              {savedPlans.length === 0 && <p className="py-6 text-center text-sm text-gray-400">暂无历史方案</p>}
              {savedPlans.map((sp) => (
                <div
                  key={sp.id}
                  onClick={() => loadPlan(sp.id)}
                  className="group flex cursor-pointer items-center justify-between rounded-lg border bg-white px-3 py-2.5 text-sm hover:border-blue-200 hover:bg-blue-50/50"
                  title="点击加载此方案进行修改"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                      {new Date(sp.created_at * 1000).getFullYear()}年
                    </span>
                    <span className="font-medium text-gray-800">{planLabel(sp.created_at)}</span>
                    <span className="text-xs text-gray-400">{planFullTime(sp.created_at)}</span>
                    <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">
                      {formatScoreRank(sp.score, sp.rank) || "—"}
                    </span>
                    <span className="shrink-0 text-xs text-gray-500">{sp.slots_count}/{sp.groups || "—"}</span>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteSavedPlan(sp.id); }}
                    className="shrink-0 rounded p-1 text-gray-300 hover:bg-red-100 hover:text-red-600"
                    title="移入回收站"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {historyTab === "trash" && (
            <div className="space-y-2">
              {trashPlans.length === 0 && <p className="py-6 text-center text-sm text-gray-400">回收站暂无内容</p>}
              {trashPlans.map((sp) => (
                <div
                  key={sp.id}
                  className="flex items-center justify-between rounded-lg border bg-white px-3 py-2.5 text-sm"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                      {new Date(sp.created_at * 1000).getFullYear()}年
                    </span>
                    <span className="font-medium text-gray-400 line-through decoration-gray-300">{planLabel(sp.created_at)}</span>
                    <span className="text-xs text-gray-400">{planFullTime(sp.created_at)}</span>
                    <span className="shrink-0 text-xs text-gray-500">{sp.slots_count}/{sp.groups || "—"}</span>
                    <span className="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-600">剩余{sp.remaining_days ?? 7}天</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      onClick={() => restoreSavedPlan(sp.id)}
                      className="rounded bg-green-50 px-2 py-1 text-xs text-green-600 hover:bg-green-100"
                    >
                      恢复
                    </button>
                    <button
                      onClick={() => purgeSavedPlan(sp.id)}
                      className="rounded bg-red-50 px-2 py-1 text-xs text-red-600 hover:bg-red-100"
                    >
                      永久删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <div className="mt-8">
        <AdmissionCountdown province={province} />
      </div>

      {/* 霍兰德职业兴趣测评 */}
      <div className="mt-8 rounded-lg border bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Compass className="h-5 w-5 text-indigo-500" />
            职业兴趣测评
            <span className="text-xs font-normal text-gray-400">霍兰德 RIASEC · 12 题</span>
          </h2>
          <button onClick={() => setHollandOpen(v => !v)} className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
            {hollandOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {hollandOpen ? "收起" : "开始测评"}
          </button>
        </div>

        {hollandOpen && (
          <div className="mt-4">
            {hollandLoading && hollandQuestions.length === 0 ? (
              <p className="text-sm text-gray-400">加载题目中…</p>
            ) : hollandResult?.result ? (
              <div>
                <div className="flex items-start justify-between">
                  <div className="flex flex-wrap gap-2">
                    {(hollandResult.result.top3_labels || []).map((label, i) => (
                      <span key={i} className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-700">{label}</span>
                    ))}
                  </div>
                  <button onClick={resetHolland} className="shrink-0 rounded-md border px-2.5 py-1 text-xs text-gray-500 hover:bg-gray-50">重新测评</button>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-3">
                  {Object.entries(hollandResult.result.scores || {}).map(([code, val]) => (
                    <div key={code} className="rounded border bg-gray-50 p-2">
                      <div className="flex items-center justify-between text-xs text-gray-500">
                        <span className="font-medium">{code}</span>
                        <span>{val as number} 分</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-gray-200">
                        <div className="h-2 rounded-full bg-indigo-500" style={{ width: `${Math.min(100, ((val as number) / 10) * 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>

                {hollandResult.major_recommendations && hollandResult.major_recommendations.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-gray-700">推荐专业</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {hollandResult.major_recommendations.slice(0, 10).map((m) => (
                        <span key={m.major} className="rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1 text-sm text-indigo-700">{m.major}</span>
                      ))}
                    </div>
                  </div>
                )}

                <p className="mt-4 text-xs text-gray-400">{hollandDisclaimer || "提示：测评结果仅供参考，不构成填报依据。"}</p>
              </div>
            ) : (
              <div>
                {hollandQuestions.length === 0 && !hollandLoading && (
                  <button
                    onClick={loadHolland}
                    className="rounded-md bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700"
                  >
                    加载题目
                  </button>
                )}

                {hollandQuestions.map((q, qi) => (
                  <div key={qi} className="rounded-md border p-3">
                    <p className="text-sm font-medium text-gray-800">
                      {qi + 1}. {q.text}
                      <span className="ml-1 rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-600">{q.code}</span>
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {[
                        { v: 1, label: "非常不符合" },
                        { v: 2, label: "不太符合" },
                        { v: 3, label: "一般" },
                        { v: 4, label: "比较符合" },
                        { v: 5, label: "非常符合" },
                      ].map((o) => (
                        <button
                          key={o.v}
                          onClick={() => setHollandAnswers(prev => ({ ...prev, [qi]: o.v }))}
                          className={`rounded-md px-3 py-1 text-xs ${hollandAnswers[qi] === o.v ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
                        >
                          {o.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}

                <button
                  onClick={submitHolland}
                  disabled={hollandLoading}
                  className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {hollandLoading ? "提交中…" : "提交测评"}
                </button>
                {hollandMsg && <p className="mt-2 text-sm text-red-500">{hollandMsg}</p>}
                {hollandDisclaimer && <p className="mt-3 text-xs text-gray-400">{hollandDisclaimer}</p>}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-8 rounded-lg border bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Sliders className="h-5 w-5 text-gray-500" />
            权重配置
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={autoTune}
              disabled={autoTuning}
              className="inline-flex items-center gap-1 rounded-md border border-purple-300 px-3 py-1.5 text-sm text-purple-700 hover:bg-purple-50 disabled:opacity-50"
            >
              <Zap className="h-3.5 w-3.5" />
              {autoTuning ? "调优中..." : "自动调优"}
            </button>
            <button
              onClick={resetWeights}
              className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              重置
            </button>
            <button
              onClick={saveWeights}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
        <p className="mb-4 text-sm text-gray-500">
          拖动滑块调整各维度权重，或使用"自动调优"根据学习记录自动配置。调整一个维度时，其他维度自动等比缩放，保持总和 100%。
        </p>
        {weightMsg && (
          <p className="mb-3 text-sm text-blue-600">{weightMsg}</p>
        )}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {weights && Object.keys(FACTOR_LABELS).map((key) => (
            <div key={key}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span>{FACTOR_LABELS[key]}</span>
                <span className="font-mono tabular-nums text-gray-500">
                  {Math.round((weights[key] || 0) * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={weights[key] || 0}
                onChange={(e) => updateWeight(key, parseFloat(e.target.value))}
                className="w-full accent-blue-600"
              />
              <div className="mt-0.5 h-1.5 w-full rounded-full bg-gray-200">
                <div
                  className={`h-1.5 rounded-full ${FACTOR_COLORS[key] || "bg-blue-500"}`}
                  style={{ width: `${(weights[key] || 0) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Floating chat button */}
      <button
        onClick={() => { setChatOpen(true); setChatContext(undefined); }}
        className="fixed bottom-6 right-6 z-20 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg hover:bg-blue-700 transition-transform hover:scale-105"
      >
        <MessageSquare className="h-6 w-6" />
      </button>

      {/* Chat drawer */}
      <VolunteerChatDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        context={chatContext}
      />
    </div>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 rounded-full bg-gray-200">
        <div
          className={`h-2 rounded-full ${color} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-xs font-mono tabular-nums text-gray-500">
        {pct}%
      </span>
    </div>
  );
}

function ScoreDetailRow({
  label,
  score,
  color,
}: {
  label: string;
  score: number;
  color: string;
}) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-1 text-xs">
      <div className={`h-2 w-2 rounded-full ${color}`} />
      <span className="w-10 text-gray-500">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-gray-100">
        <div
          className={`h-1.5 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-6 text-right text-gray-400">{pct}%</span>
    </div>
  );
}

function AdmissionHistoryPanel({ collegeId }: { collegeId: string }) {
  const [history, setHistory] = useState<AdmissionHistoryItem[]>([]);
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (!show && history.length === 0) {
      setLoading(true);
      try {
        const res = await fetch(
          `/api/v1/volunteer/admission-history/${collegeId}?province=广东&exam_category=物理`
        );
        if (res.ok) {
          setHistory(await res.json());
        }
      } catch { /* ignore */ }
      setLoading(false);
    }
    setShow(!show);
  };

  return (
    <div className="mt-2">
      <button
        onClick={toggle}
        className="text-xs text-blue-500 hover:text-blue-700"
      >
        {show ? "收起位次趋势" : "查看位次趋势"}
      </button>
      {show && (
        <div className="mt-1.5 rounded bg-gray-50 p-2 text-xs">
          {loading && <p className="text-gray-400">加载中...</p>}
          {!loading && history.length === 0 && (
            <p className="text-gray-400">暂无历年位次数据</p>
          )}
          {!loading && history.length > 0 && (
            <div className="space-y-1">
              {history.map((h) => (
                <div key={`${h.year}-${h.batch || ''}`} className="flex justify-between">
                  <span className="text-gray-500">{h.year}年</span>
                  <span className="font-medium text-gray-700">
                    {h.min_rank > 0 ? `位次 ${h.min_rank}` : `分数 ${h.min_score}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PlanTierCard({
  title,
  icon,
  color,
  desc,
  items,
  onDragStart,
  onDragEnter,
  onDragEnd,
  onChat,
  onDelete,
}: {
  title: string;
  icon: React.ReactNode;
  color: string;
  desc: string;
  items: SlotItem[];
  onDragStart: (key: string) => void;
  onDragEnter: (key: string) => void;
  onDragEnd: () => void;
  onChat?: (item: SlotItem) => void;
  onDelete?: (index: number) => void;
}) {
  return (
    <div className="rounded-lg border bg-white p-6 shadow-sm">
      <div className={`flex items-center gap-2 ${color}`}>
        {icon}
        <h3 className="font-semibold">{title}</h3>
        {items.length > 0 && (
          <span className="ml-auto text-sm text-gray-400">{items.length}个</span>
        )}
      </div>
      <p className="mt-2 text-sm text-gray-500">{desc}</p>
      <div className="mt-4 space-y-3">
        {items.length === 0 && (
          <div className="rounded bg-gray-50 p-3 text-sm text-gray-400 italic">
            暂未添加
          </div>
        )}
        {items.map((slot, i) => {
          const groupProb = slot.group_prob ?? slot.admission_prob ?? 0;
          const tColor = slot.tier === "reach" ? "border-l-green-500 bg-green-50"
            : slot.tier === "steady" ? "border-l-yellow-500 bg-yellow-50"
            : "border-l-blue-500 bg-blue-50";
          return (
            <div
              key={`${slot.college_id}-${slot.group_code}`}
              draggable
              onDragStart={() => onDragStart(`${slot.college_id}-${slot.group_code}`)}
              onDragEnter={() => onDragEnter(`${slot.college_id}-${slot.group_code}`)}
              onDragEnd={onDragEnd}
              onDragOver={(e) => e.preventDefault()}
              className={`rounded-lg border-l-4 bg-white p-3 shadow-sm cursor-grab active:cursor-grabbing ${tColor}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex flex-wrap items-center gap-1 min-w-0">
                  <GripVertical className="h-4 w-4 shrink-0 text-gray-300" />
                  <span className="font-medium text-gray-900">{slot.college_name}</span>
                  {slot.province_code && (
                    <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600" title="本省招生代码">
                      代码 {slot.province_code}
                    </span>
                  )}
                  {slot.group_code && (
                    <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                      {slot.group_name || `${slot.group_code}组`}
                    </span>
                  )}
                  {(slot.bargain_score ?? 0) >= 0.6 && (
                    <span className="shrink-0 rounded bg-orange-100 px-1.5 py-0.5 text-xs text-orange-600">捡漏</span>
                  )}
                  {slot.rank_source === "estimated" && (
                    <span className="shrink-0 rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-600" title="该专业组无官方投档位次，位次为预估">预估位次</span>
                  )}
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${slot.tier === "reach" ? "bg-green-100 text-green-700" : slot.tier === "steady" ? "bg-yellow-100 text-yellow-700" : "bg-blue-100 text-blue-700"}`}>
                    #{slot.order}
                  </span>
                  {onDelete && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onDelete(i); }}
                      className="ml-1 shrink-0 rounded p-0.5 text-gray-400 hover:bg-red-100 hover:text-red-600"
                      title="移除此志愿"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  )}
                </div>
                <span className="whitespace-nowrap text-sm font-bold text-blue-600">
                  {Math.round(groupProb * 100)}%
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full rounded-full bg-gray-200">
                <div className={`h-1.5 rounded-full ${groupProb >= 0.8 ? "bg-green-500" : groupProb >= 0.45 ? "bg-yellow-500" : "bg-red-400"}`}
                  style={{ width: `${Math.round(groupProb * 100)}%` }} />
              </div>
              {slot.majors && slot.majors.length > 0 && (
                <div className="mt-2 space-y-1">
                  {slot.majors.map((mj: Partial<SlotMajor>, mi: number) => {
                    const tagColor = mj.tag === "推荐" ? "bg-green-100 text-green-700"
                      : mj.tag === "优选" ? "bg-yellow-100 text-yellow-700"
                      : "bg-gray-100 text-gray-500";
                    return (
                      <div key={mi} className="flex items-center justify-between rounded bg-white/60 px-2 py-1 text-xs">
                        <span className="min-w-0">
                          <span className="text-gray-700">{mj.major_name || ""}</span>
                          {mj.tag && <span className={`ml-1.5 rounded px-1 py-0.5 ${tagColor}`}>{mj.tag}</span>}
                          <span className="ml-1.5 text-[10px] text-gray-400">{formatMajorMeta(mj)}</span>
                        </span>
                        {mj.admission_prob != null && (
                          <span className="text-gray-400">{Math.round(mj.admission_prob * 100)}%</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              <label className="mt-2 flex items-center gap-1.5 text-xs text-gray-500">
                <input type="checkbox" defaultChecked={slot.adjustable !== false} className="accent-blue-600" />
                服从专业调剂
              </label>
              {onChat && (
                <button
                  onClick={(e) => { e.stopPropagation(); onChat(slot); }}
                  className="mt-2 inline-flex items-center gap-1 rounded-md border border-blue-200 px-2.5 py-1 text-xs text-blue-600 hover:bg-blue-50"
                >
                  <MessageSquare className="h-3 w-3" />
                  AI 咨询
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


const MIN_SCORE = 0;
const MAX_SCORE = 750;

function ScoreDistributionChart({
  province,
  examCategory,
  currentScore,
  onRangeChange,
  onReset,
}: {
  province: string;
  examCategory: string;
  currentScore: number | null;
  onRangeChange: (minScore: number, maxScore: number) => void;
  onReset?: () => void;
}) {
  const [buckets, setBuckets] = useState<{ score_low: number; score_high: number; count: number }[]>([]);
  const [minScore, setMinScore] = useState(400);
  const [maxScore, setMaxScore] = useState(600);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/v1/volunteer/score-distribution?province=${encodeURIComponent(province)}&exam_category=${encodeURIComponent(examCategory)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.buckets) {
          setBuckets(d.buckets);
          if (d.buckets.length > 0) {
            const lows = (d.buckets as Array<{score_low: number}>).map(b => b.score_low);
            const highs = (d.buckets as Array<{score_high: number}>).map(b => b.score_high);
            setMinScore(Math.min(...lows));
            setMaxScore(Math.max(...highs));
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [province, examCategory]);

  useEffect(() => {
    if (currentScore !== null && buckets.length > 0) {
      const clamped = Math.max(buckets[0].score_low, Math.min(currentScore, buckets[buckets.length - 1].score_high));
      const low = Math.max(buckets[0].score_low, clamped - 20);
      const high = Math.min(buckets[buckets.length - 1].score_high, clamped + 20);
      setMinScore(low);
      setMaxScore(high);
    }
  }, [currentScore, buckets]);

  const chartData = {
    labels: buckets.map((b) => `${b.score_low}`),
    datasets: [
      {
        label: "专业组数量",
        data: buckets.map((b) => b.count),
        backgroundColor: buckets.map((b) =>
          b.score_low >= minScore && b.score_low < maxScore
            ? "rgba(59, 130, 246, 0.7)"
            : "rgba(156, 163, 175, 0.3)",
        ),
        borderColor: buckets.map((b) =>
          b.score_low >= minScore && b.score_low < maxScore
            ? "rgb(59, 130, 246)"
            : "rgb(209, 213, 219)",
        ),
        borderWidth: 1,
        borderRadius: 2,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items: any) => `${items[0].label} 分`,
          label: (item: any) => ` ${item.raw} 个专业组`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 20,
          font: { size: 10 },
        },
      },
      y: {
        grid: { color: "rgba(0,0,0,0.05)" },
        ticks: { font: { size: 10 } },
        beginAtZero: true,
      },
    },
  };

  const totalInRange = buckets
    .filter((b) => b.score_low >= minScore && b.score_low < maxScore)
    .reduce((s, b) => s + b.count, 0);

  useEffect(() => {
    onRangeChange(minScore, maxScore);
  }, [minScore, maxScore, onRangeChange]);

  const handleMinSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    setMinScore(Math.min(v, maxScore - 10));
  };
  const handleMaxSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    setMaxScore(Math.max(v, minScore + 10));
  };

  if (loading) {
    return <div className="mt-2 text-sm text-gray-400">加载分布数据...</div>;
  }
  if (buckets.length === 0) return null;

  return (
    <div className="mt-2 rounded-lg border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">
          区间 {minScore}-{maxScore} 分 &middot; {totalInRange} 个专业组
        </span>
        <span className="text-xs text-gray-400">拖动滑块自动更新</span>
      </div>
      <div style={{ height: 180 }}>
        <Bar data={chartData} options={chartOptions} />
      </div>
      <div className="relative mt-3" style={{ height: 32 }}>
        <input
          type="range"
          min={buckets[0].score_low}
          max={buckets[buckets.length - 1].score_high}
          value={minScore}
          onChange={handleMinSlider}
          className="pointer-events-auto absolute left-0 top-0 h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-200 accent-blue-600 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:shadow"
          style={{ zIndex: 3, background: "transparent" }}
        />
        <input
          type="range"
          min={buckets[0].score_low}
          max={buckets[buckets.length - 1].score_high}
          value={maxScore}
          onChange={handleMaxSlider}
          className="pointer-events-auto absolute left-0 top-0 h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-200 accent-blue-600 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-600 [&::-webkit-slider-thumb]:shadow"
          style={{ zIndex: 2, background: "transparent" }}
        />
        <div className="pointer-events-none absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full bg-gray-200">
          <div
            className="h-full rounded-full bg-blue-300"
            style={{
              marginLeft: `${((minScore - buckets[0].score_low) / (buckets[buckets.length - 1].score_high - buckets[0].score_low)) * 100}%`,
              width: `${((maxScore - minScore) / (buckets[buckets.length - 1].score_high - buckets[0].score_low)) * 100}%`,
            }}
          />
        </div>
      </div>
      <div className="mt-1 flex justify-between text-xs text-gray-400">
        <span>{buckets[0].score_low} 分</span>
        <span>{buckets[buckets.length - 1].score_high}+ 分</span>
      </div>
      <div className="mt-3 flex justify-center">
        <button
          onClick={onReset}
          className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          重置区间
        </button>
      </div>
    </div>
  );
}
