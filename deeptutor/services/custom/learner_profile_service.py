"""学习者画像引擎 —— 辅助学习与升学推荐的「有机结合」枢纽。

画像数据流（单向增强，双向使用）：
```
错题本(mistakes) ──┐
study_records  ────┼──► compute_learner_profile() ──► subject_mastery / 薄弱点 / 专业倾向
L3 记忆(可选) ─────┘                    │
                                        ├─► build_academic_fit_inputs() ──► 升学推荐 _calc_academic_fit
                                        ├─► recommend_majors_by_profile() ──► 「适合的专业」推荐
                                        ├─► apply_profile_to_volunteer()  ──► user_settings + L3 写回
                                        └─► 前端 /study 画像面板
```

设计原则：
- **确定性计算**：掌握度 = 成绩正确率 − 未掌握错题惩罚，全部可解释，不依赖 LLM 幻觉
- **结构兼容**：`build_academic_fit_inputs()` 输出的 `_subjects` / `_learner_profile`
  与 `capabilities/volunteer/loop.py` 注入的字段结构完全一致，
  因此 `volunteer_scorer._calc_academic_fit` **零改动**即可消费错题本画像。
"""

from __future__ import annotations

import json
import time
from typing import Any

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.study_dao import get_subject_summary

# 学科画像强弱阈值（与 adaptive_weights.SUBJECT_CATEGORIES 互补）
STRONG_THRESHOLD = 0.75
WEAK_THRESHOLD = 0.50
# 每个未掌握错题的掌握度惩罚（上限封顶，避免单科被压到 0）
MISTAKE_PENALTY_PER_OPEN = 0.12
MISTAKE_PENALTY_CAP = 0.45


def compute_learner_profile(user_id: str) -> dict[str, Any]:
    """实时计算学习者画像（纯 SQL，可重复调用）。

    返回结构：
    {
      "subject_mastery": {科目: {"accuracy": float, "sample_count": int, "source": str}},
      "weak_knowledge_points": [{"point", "subject", "fail_count", "avg_mastery"}],
      "strong_knowledge_points": [{"point", "subject", "success_count"}],
      "strengths": [科目], "weaknesses": [科目],
      "preferred_majors": [{"major_id", "major_name", "fit_score"}],
      "profile_summary": str,          # 供 LLM / 前端展示的文本
      "confidence": float,             # 0~1 画像置信度
      "stats": {"records", "mistakes", "open_mistakes", "reviews"},
    }
    """
    subjects = get_subject_summary(user_id)
    mistakes, open_counts, mastered_counts = _load_mistakes(user_id)
    reviews = _load_review_count(user_id)

    # 1) 学科掌握度：成绩正确率 − 错题惩罚；无成绩的科目用错题倒推
    subject_mastery: dict[str, dict[str, Any]] = {}
    for s in subjects:
        name = str(s.get("subject", ""))
        acc = s.get("avg_accuracy")
        if not name or acc is None:
            continue
        count = int(s.get("count", 0))
        open_n = open_counts.get(name, 0)
        mastered_n = mastered_counts.get(name, 0)
        penalty = min(MISTAKE_PENALTY_CAP, MISTAKE_PENALTY_PER_OPEN * open_n)
        bonus = min(0.10, 0.02 * mastered_n)
        mastery = max(0.05, min(0.98, float(acc) - penalty + bonus))
        subject_mastery[name] = {
            "accuracy": round(mastery, 3),
            "sample_count": count + open_n,
            "source": "records+mistakes" if open_n else "study_records",
        }
    for subj, open_n in open_counts.items():
        if subj and subj not in subject_mastery:
            estimate = max(0.10, 1.0 - min(MISTAKE_PENALTY_CAP, MISTAKE_PENALTY_PER_OPEN * open_n))
            subject_mastery[subj] = {
                "accuracy": round(estimate, 3),
                "sample_count": open_n,
                "source": "mistakes",
            }

    # 2) 强弱知识点
    weak_kps, strong_kps = _aggregate_knowledge_points(mistakes)

    # 3) 学科强弱（供 _calc_academic_fit 的 _learner_profile 分支使用）
    strengths = [s for s, m in subject_mastery.items() if m["accuracy"] >= STRONG_THRESHOLD]
    weaknesses = [s for s, m in subject_mastery.items() if m["accuracy"] <= WEAK_THRESHOLD]

    # 4) 专业倾向：subject_major_map 权重 × 学科掌握度
    preferred_majors = _score_majors(subject_mastery)

    total_samples = sum(m["sample_count"] for m in subject_mastery.values())
    confidence = min(1.0, total_samples / 30.0)

    profile_summary = _format_summary(subject_mastery, weak_kps, strengths, weaknesses)

    stats = {
        "records": len(subjects),
        "mistakes": len(mistakes),
        "open_mistakes": sum(open_counts.values()),
        "reviews": reviews,
    }
    return {
        "user_id": user_id,
        "subject_mastery": subject_mastery,
        "weak_knowledge_points": weak_kps,
        "strong_knowledge_points": strong_kps,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "preferred_majors": preferred_majors,
        "profile_summary": profile_summary,
        "confidence": round(confidence, 3),
        "stats": stats,
        "updated_at": time.time(),
    }


def build_academic_fit_inputs(
    user_id: str,
    l3_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """输出升学推荐引擎可直接消费的注入参数（核心有机结合点）。

    **画像分层互补**（消除「原生 L3 画像」与「错题本画像」的冲突）：
      - 定量层（错题本 + 成绩，确定性计算）→ `_subjects` + strengths/weaknesses/知识点
      - 定性层（L3 原生记忆，LLM 归纳）→ identity/learning_style/knowledge_level/goals/偏好
      - 合成：两组字段**键不重叠**，合并即互补，不互相覆盖

    返回结构兼容 `volunteer_scorer._calc_academic_fit` 的优先链：
      - `_subjects`: [{"subject", "count", "avg_accuracy", "source"}]  ← 学科掌握度（定量）
      - `_learner_profile`: 定性 + 定量合并后的 dict

    前端 browse / recommend 与 chat agent 循环**共用此函数**，画像口径一致。

    Args:
        user_id: 用户 id
        l3_profile: 可选，预读的 L3 定性画像（避免重复读盘）；为 None 时内部读取。
    """
    profile = compute_learner_profile(user_id)

    if l3_profile is None:
        from deeptutor.services.custom.memory_bridge import read_l3_profile

        l3_profile = read_l3_profile()

    subjects = [
        {
            "subject": name,
            "count": m["sample_count"],
            "avg_accuracy": m["accuracy"],
            "source": m.get("source", "study_records"),
        }
        for name, m in profile["subject_mastery"].items()
    ]

    learner_profile = {
        # ── 定性层（L3 原生记忆）──
        "identity": l3_profile.get("identity", []),
        "learning_style": l3_profile.get("learning_style", []),
        "knowledge_level": l3_profile.get("knowledge_level", []),
        "goals": l3_profile.get("goals", []),
        "career_interests": l3_profile.get("career_interests", []),
        "location_prefs": l3_profile.get("location_prefs", []),
        "other_preferences": l3_profile.get("other_preferences", []),
        "other_profile": l3_profile.get("other_profile", []),
        "qualitative_source": "l3",
        # ── 定量层（错题本 + 成绩，确定性计算）──
        "strengths": profile["strengths"],
        "weaknesses": profile["weaknesses"],
        "weak_knowledge_points": profile["weak_knowledge_points"],
        "strong_knowledge_points": profile["strong_knowledge_points"],
        "quantitative_source": "mistakes",
    }
    return {"_subjects": subjects, "_learner_profile": learner_profile}


def recommend_majors_by_profile(user_id: str, top_n: int = 10) -> list[dict[str, Any]]:
    """画像 → 「适合的专业」倾向推荐（升学侧专业筛选的画像维度）。"""
    profile = compute_learner_profile(user_id)
    return profile["preferred_majors"][: max(1, top_n)]


def save_profile(user_id: str) -> dict[str, Any]:
    """计算并持久化画像到 learner_profiles 表（供升学侧 / 前端读取）。"""
    profile = compute_learner_profile(user_id)
    conn = get_connection()
    conn.execute(
        """INSERT INTO learner_profiles (user_id, profile_json, confidence, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               profile_json = excluded.profile_json,
               confidence = excluded.confidence,
               updated_at = excluded.updated_at""",
        (user_id, json.dumps(profile, ensure_ascii=False), profile["confidence"], time.time()),
    )
    conn.commit()
    conn.close()
    return profile


def load_profile(user_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT profile_json FROM learner_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row["profile_json"])


async def apply_profile_to_volunteer(user_id: str) -> dict[str, Any]:
    """把学习画像「应用到升学」：持久化 + 写 user_settings 供升学侧读取。

    写方向（学习 → 升学）：
      1. 持久化画像缓存（learner_profiles 表）
      2. 写入 user_settings（volunteer 读取的 profile 快照）

    注意：**不写回 L3 preferences**。错题本画像是确定性计算产物，
    而 L3 preferences 是原生记忆策展员/用户原话的领地；写回会污染原生记忆
    （且 preferences.md 不做自动合并，会持续堆积）。定性画像由 L3 单向供给，
    定量画像由本模块单向供给，两者在 `build_academic_fit_inputs()` 中合并。
    """
    profile = save_profile(user_id)

    conn = get_connection()
    row = conn.execute(
        "SELECT settings_json FROM user_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    settings = json.loads(row["settings_json"]) if row else {}
    settings["learner_profile"] = {
        "subject_mastery": profile["subject_mastery"],
        "weak_knowledge_points": profile["weak_knowledge_points"][:20],
        "preferred_majors": profile["preferred_majors"][:10],
        "profile_summary": profile["profile_summary"],
        "updated_at": profile["updated_at"],
        "confidence": profile["confidence"],
    }
    now = time.time()
    conn.execute(
        """INSERT INTO user_settings (user_id, settings_json, created_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               settings_json = excluded.settings_json,
               updated_at = excluded.updated_at""",
        (user_id, json.dumps(settings, ensure_ascii=False), now, now),
    )
    conn.commit()
    conn.close()

    return profile


# ─────────────────────────── 内部工具 ───────────────────────────


def _load_mistakes(user_id: str) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    """返回 (错题列表, 各科未掌握数, 各科已掌握数)。"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT subject, knowledge_points, mastery, status FROM mistakes
           WHERE user_id = ? AND status != 'archived'""",
        (user_id,),
    ).fetchall()
    conn.close()
    mistakes: list[dict[str, Any]] = []
    open_counts: dict[str, int] = {}
    mastered_counts: dict[str, int] = {}
    for r in rows:
        subject = str(r["subject"] or "")
        kps = json.loads(r["knowledge_points"] or "[]")
        item = {
            "subject": subject,
            "knowledge_points": [str(k) for k in kps],
            "mastery": float(r["mastery"] or 0.3),
            "status": r["status"],
        }
        mistakes.append(item)
        if r["status"] == "mastered":
            mastered_counts[subject] = mastered_counts.get(subject, 0) + 1
        else:
            open_counts[subject] = open_counts.get(subject, 0) + 1
    return mistakes, open_counts, mastered_counts


def _load_review_count(user_id: str) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM mistake_reviews WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return int(row["c"])


def _aggregate_knowledge_points(
    mistakes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    weak: dict[str, dict[str, Any]] = {}
    strong: dict[str, dict[str, Any]] = {}
    for m in mistakes:
        subject = m.get("subject", "")
        mastery = m.get("mastery", 0.3)
        for kp in m.get("knowledge_points", []):
            kp = str(kp).strip()
            if not kp:
                continue
            if mastery < 0.6:
                entry = weak.setdefault(kp, {"point": kp, "subject": subject, "fail_count": 0, "mastery_sum": 0.0, "count": 0})
                entry["fail_count"] += 1
                entry["mastery_sum"] += mastery
                entry["count"] += 1
            else:
                entry = strong.setdefault(kp, {"point": kp, "subject": subject, "success_count": 0})
                entry["success_count"] += 1
    weak_list = []
    for entry in weak.values():
        entry["avg_mastery"] = round(entry["mastery_sum"] / entry["count"], 3)
        weak_list.append(entry)
    weak_list.sort(key=lambda x: -x["fail_count"])
    strong_list = sorted(strong.values(), key=lambda x: -x["success_count"])
    return weak_list[:50], strong_list[:50]


def _score_majors(subject_mastery: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """用 subject_major_map 的学科权重 × 学科掌握度计算专业匹配分。"""
    from deeptutor.services.custom.subject_major_map import SUBJECT_WEIGHTS

    majors = _load_major_names()
    scored: list[dict[str, Any]] = []
    for major_id, weights in SUBJECT_WEIGHTS.items():
        total_w = 0.0
        weighted = 0.0
        for subject, w in weights.items():
            m = subject_mastery.get(subject)
            acc = m["accuracy"] if m else 0.5  # 无数据的学科按中性 0.5
            weighted += w * acc
            total_w += w
        if total_w <= 0:
            continue
        fit = round(weighted / total_w, 4)
        scored.append({
            "major_id": major_id,
            "major_name": majors.get(major_id, major_id),
            "fit_score": fit,
        })
    scored.sort(key=lambda x: -x["fit_score"])
    return scored


def _load_major_names() -> dict[str, str]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM majors").fetchall()
    conn.close()
    return {r["id"]: r["name"] for r in rows}


def _format_summary(
    subject_mastery: dict[str, dict[str, Any]],
    weak_kps: list[dict[str, Any]],
    strengths: list[str],
    weaknesses: list[str],
) -> str:
    parts: list[str] = []
    if strengths:
        parts.append("学科优势: " + "、".join(strengths))
    if weaknesses:
        parts.append("薄弱学科: " + "、".join(weaknesses))
    if subject_mastery:
        acc_lines = [f"{k}{v['accuracy']*100:.0f}%" for k, v in sorted(subject_mastery.items(), key=lambda x: -x[1]['accuracy'])]
        parts.append("学科掌握度: " + " | ".join(acc_lines))
    if weak_kps:
        points = "、".join(w["point"] for w in weak_kps[:5])
        parts.append(f"待巩固知识点: {points}")
    return "；".join(parts) if parts else "暂无足够学习数据，画像待完善"
