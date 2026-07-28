from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS


def _normalize(value: float, min_v: float, max_v: float) -> float:
    if max_v <= min_v:
        return 0.5
    return max(0.0, min(1.0, (value - min_v) / (max_v - min_v)))


WEIGHT_KEYS = ["dorm_quality", "city_vitality", "cost_efficiency", "employment", "admission_prob", "academic_fit"]


def score_college_major(
    college: dict[str, Any],
    major: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
    strategy: str | list[str] | None = None,
) -> dict[str, Any]:
    w = _resolve_strategy_weights(weights, strategy or "default")
    user_profile = user_profile or {}
    raw: dict[str, float] = {}
    explanations: dict[str, str] = {}
    evidence: dict[str, Any] = {}

    college_dorm = float(college.get("dorm_score", 0) or 0)
    raw["dorm_quality"] = _normalize(college_dorm, 0, 10)
    explanations["dorm_quality"] = _explain_dorm(college_dorm)

    city_vitality = float(college.get("city_vitality", 0) or 0)
    raw["city_vitality"] = _normalize(city_vitality, 0, 10)
    explanations["city_vitality"] = _explain_city(city_vitality)

    cost_idx = float(college.get("cost_index", 1) or 1)
    raw["cost_efficiency"] = _normalize(1.0 / max(cost_idx, 0.1), 0.5, 2.0)
    explanations["cost_efficiency"] = _explain_cost(cost_idx)

    emp_rate = float(college.get("employment_rate", 0) or 0)
    raw["employment"] = _normalize(emp_rate, 0, 1)
    explanations["employment"] = _explain_employment(emp_rate)

    college_id = college.get("id")
    if major:
        admission_prob, prob_evidence = _calc_admission_prob(major, user_profile, college_id)
        raw["admission_prob"] = admission_prob
        explanations["admission_prob"] = _explain_admission(admission_prob)
        evidence.update({"admission_" + k: v for k, v in prob_evidence.items()})

        academic_fit_val = _calc_academic_fit(major, user_profile)
        raw["academic_fit"] = academic_fit_val
        explanations["academic_fit"] = _explain_academic_fit(academic_fit_val)
    else:
        admission_prob, prob_evidence = _calc_admission_prob({}, user_profile, college_id)
        raw["admission_prob"] = admission_prob
        explanations["admission_prob"] = _explain_admission(admission_prob)
        evidence.update({"admission_" + k: v for k, v in prob_evidence.items()})

        raw["academic_fit"] = 0.5
        explanations["academic_fit"] = "未选择专业，学业匹配度取默认值"

    bargain = _calc_bargain_score(college_id, user_profile)
    raw["bargain_score"] = bargain
    evidence["bargain_score"] = round(bargain, 4)
    evidence["bargain_note"] = _explain_bargain(bargain)

    total = sum(raw.get(k, 0) * w.get(k, 0) for k in WEIGHT_KEYS)
    return {
        "total_score": round(total, 4),
        "detail_scores": {k: round(v, 4) for k, v in raw.items()},
        "explanations": explanations,
        "evidence": evidence,
    }


STRATEGY_PRESETS: dict[str, dict[str, float]] = {
    "default": VOLUNTEER_DEFAULT_WEIGHTS,
    "admission_only": {
        "academic_fit": 0.0,
        "admission_prob": 1.0,
        "dorm_quality": 0.0,
        "city_vitality": 0.0,
        "cost_efficiency": 0.0,
        "employment": 0.0,
        "career_alignment": 0.0,
    },
    "college_first": VOLUNTEER_DEFAULT_WEIGHTS,
    "major_first": {
        "academic_fit": 0.35,
        "admission_prob": 0.20,
        "dorm_quality": 0.05,
        "city_vitality": 0.05,
        "cost_efficiency": 0.05,
        "employment": 0.20,
        "career_alignment": 0.10,
    },
    "city_first": {
        "academic_fit": 0.20,
        "admission_prob": 0.20,
        "dorm_quality": 0.10,
        "city_vitality": 0.25,
        "cost_efficiency": 0.10,
        "employment": 0.10,
        "career_alignment": 0.05,
    },
}


def _resolve_strategy_weights(
    weights: dict[str, float] | None, strategies: str | list[str] | None = None
) -> dict[str, float]:
    if weights:
        return weights
    if isinstance(strategies, str):
        strategies = [strategies] if strategies else ["default"]
    if not strategies:
        strategies = ["default"]
    if len(strategies) == 1:
        return dict(STRATEGY_PRESETS.get(strategies[0], VOLUNTEER_DEFAULT_WEIGHTS))
    from collections import defaultdict
    merged: dict[str, float] = defaultdict(float)
    for s in strategies:
        w = STRATEGY_PRESETS.get(s, VOLUNTEER_DEFAULT_WEIGHTS)
        for k, v in w.items():
            merged[k] += v
    return {k: v / len(strategies) for k, v in merged.items()}


def generate_recommendations(
    colleges: list[dict[str, Any]],
    user_profile: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
    top_n: int = 10,
    default_major: dict[str, Any] | None = None,
    strategy: str | list[str] | None = None,
    min_safe: int = 2,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    for c in colleges:
        major = c.get("major") or default_major
        result = score_college_major(c, major=major, user_profile=user_profile, weights=weights, strategy=strategy)
        scored.append({"college": c, **result})

    all_safe, all_steady, all_reach = _split_tiers(scored)

    all_safe.sort(key=lambda x: -x["total_score"])
    all_steady.sort(key=lambda x: -x["total_score"])
    all_reach.sort(key=lambda x: -x["total_score"])

    per_tier = max(1, top_n // 3)
    safe = all_safe[:max(per_tier, min_safe)]
    steady = all_steady[:per_tier]
    reach = all_reach[:per_tier]

    safe = all_safe[:max(per_tier, min_safe)]

    remaining = top_n - (len(safe) + len(steady) + len(reach))
    if remaining > 0:
        extra = []
        for lst in (all_safe[max(per_tier, min_safe):], all_steady[per_tier:], all_reach[per_tier:]):
            extra.extend(lst)
        extra.sort(key=lambda x: -x["total_score"])
        for item in extra[:remaining]:
            prob = item["detail_scores"]["admission_prob"]
            if prob >= 0.8:
                safe.append(item)
            elif prob >= 0.45:
                steady.append(item)
            else:
                reach.append(item)

    return {
        "recommendations": safe + steady + reach,
        "tiers": {
            "reach": reach,
            "steady": steady,
            "safe": safe,
        },
    }


def _split_tiers(
    scored: list[dict[str, Any]]
) -> tuple[list[dict], list[dict], list[dict]]:
    safe: list[dict] = []
    steady: list[dict] = []
    reach: list[dict] = []
    for item in scored:
        prob = item.get("detail_scores", {}).get("admission_prob", 0)
        if prob >= 0.8:
            safe.append(item)
        elif prob >= 0.45:
            steady.append(item)
        else:
            reach.append(item)
    return safe, steady, reach


def _calc_admission_prob(
    major: dict[str, Any], profile: dict[str, Any], college_id: str | None = None,
    group_code: str | None = None, preloaded_ranks: list[dict] | None = None,
    total_cand: int = 0,
) -> tuple[float, dict[str, Any]]:
    user_rank = profile.get("rank")
    if not user_rank:
        return 0.5, {"reason": "无位次数据，使用默认概率"}
    province = profile.get("province")
    exam_category = profile.get("exam_category")
    if not province or not exam_category:
        return 0.5, {"reason": "缺少省份或选考科目，使用默认概率"}

    if not total_cand:
        from deeptutor.services.custom.admission_dao import (
            get_total_candidates,
        )
        total_cand = get_total_candidates(province, 2025, exam_category)
    if not total_cand:
        return 0.5, {"reason": "无考生总数数据，使用默认概率"}

    p_cand = user_rank / total_cand
    major_id = major.get("id") or major.get("major_id")

    min_ranks: list[float] = []
    years_data: dict[int, dict[str, Any]] = {}
    if province and college_id:
        try:
            rows = preloaded_ranks or []
            if not rows:
                from deeptutor.services.custom.admission_dao import (
                    get_admission_ranks, get_admission_ranks_by_college,
                )
                rows = get_admission_ranks(college_id, major_id or "GEN", province, exam_category=exam_category, group_code=group_code)
                if not rows:
                    rows = get_admission_ranks(college_id, major_id or "GEN", province, exam_category=exam_category)
                if not rows:
                    rows = get_admission_ranks_by_college(college_id, province, exam_category=exam_category, group_code=group_code)
                if not rows and group_code is not None:
                    rows = get_admission_ranks_by_college(college_id, province, exam_category=exam_category)

            year_best: dict[int, int] = {}
            for r in rows:
                rk = int(r["min_rank"]) if r.get("min_rank", 0) > 0 else 0
                yr = int(r["year"])
                if rk > 0:
                    if yr not in year_best or rk < year_best[yr]:
                        year_best[yr] = rk
            for yr, rk in sorted(year_best.items(), key=lambda x: -x[0]):
                from deeptutor.services.custom.admission_dao import (
                    get_total_candidates,
                )
                yr_total = get_total_candidates(province, yr, exam_category)
                if not yr_total and total_cand:
                    yr_total = total_cand
                if yr_total:
                    weight = {2026: 0.5, 2025: 0.35, 2024: 0.15}.get(yr, 0.1)
                    pct = rk / yr_total
                    min_ranks.extend([pct] * int(weight * 10))
                    years_data[str(yr)] = {"percentile": round(pct, 4), "total_candidates": yr_total}
        except Exception:
            pass

    if not min_ranks:
        for year in (2026, 2025, 2024):
            r = major.get(f"min_rank_{year}")
            if r and int(r) > 0:
                yr_total = get_total_candidates(province, year, exam_category)
                if not yr_total:
                    yr_total = total_cand
                if yr_total:
                    min_ranks.append(int(r) / yr_total)

    if not min_ranks:
        return 0.5, {"reason": "无录取位次数据，使用默认概率"}

    mu_g = sum(min_ranks) / len(min_ranks)
    sigma_g = max(0.02, (max(min_ranks) - min(min_ranks)) / 2.0) if len(min_ranks) > 1 else 0.05

    prob = 0.5 * (1.0 + math.erf((mu_g - p_cand) / (sigma_g * math.sqrt(2.0))))
    prob = max(0.05, min(0.95, prob))

    n_data_points = len(min_ranks)
    confidence = "high" if n_data_points >= 15 else "medium" if n_data_points >= 5 else "low"

    evidence = {
        "num_years": len(years_data) if years_data else 1,
        "data_points": n_data_points,
        "confidence": confidence,
        "percentile": round(p_cand, 4),
        "years_used": years_data if years_data else {"fallback": "major字段"},
    }
    return prob, evidence


def _calc_bargain_score(college_id: str | None, profile: dict[str, Any]) -> float:
    if not college_id:
        return 0.0
    province = profile.get("province")
    exam_category = profile.get("exam_category")
    if not province or not exam_category:
        return 0.0
    from deeptutor.services.custom.admission_dao import (
        get_admission_ranks_by_college,
        get_total_candidates,
    )
    try:
        rows = get_admission_ranks_by_college(college_id, province, exam_category=exam_category)
        year_ranks: dict[int, int] = {}
        for r in rows:
            yr = int(r["year"])
            rk = int(r["min_rank"]) if r.get("min_rank", 0) > 0 else 0
            if rk > 0:
                if yr not in year_ranks or rk < year_ranks[yr]:
                    year_ranks[yr] = rk
        if len(year_ranks) < 2:
            return 0.0
        vals = list(year_ranks.values())
        mean_r = sum(vals) / len(vals)
        std_r = (max(vals) - min(vals)) / 2.0 if len(vals) > 1 else mean_r * 0.1
        if std_r == 0:
            return 0.0
        latest_rank = max(year_ranks.items(), key=lambda x: x[0])[1]
        # If latest rank is significantly lower (more competitive) -> bargain opportunity
        z = (mean_r - latest_rank) / std_r
        return max(0.0, min(1.0, z / 3.0))
    except Exception:
        return 0.0


def _calc_academic_fit(
    major: dict[str, Any], profile: dict[str, Any]
) -> float:
    major_id = major.get("id") or major.get("major_id")
    if not major_id:
        return 0.5

    from deeptutor.services.custom.subject_major_map import SUBJECT_WEIGHTS
    weights = SUBJECT_WEIGHTS.get(major_id)
    if not weights:
        return 0.5

    user_id = profile.get("user_id") or "default"

    # Priority 1: injected _subjects (from agent loop context)
    subjects = profile.get("_subjects")
    if subjects is None:
        # Priority 2: direct DB fallback
        try:
            from deeptutor.services.custom.study_dao import get_subject_summary
            subjects = get_subject_summary(user_id)
        except Exception:
            subjects = []

    # Build subject accuracy map from study records
    subject_accuracy: dict[str, float] = {}
    if subjects:
        for s in subjects:
            name = str(s.get("subject", ""))
            acc = s.get("avg_accuracy")
            if name and acc is not None:
                subject_accuracy[name] = float(acc)

    # Priority 3: supplement with L3 learner_profile cold start estimates
    learner_profile = profile.get("_learner_profile")
    if learner_profile:
        for strong in learner_profile.get("strengths", []):
            # "Strong in 数学" -> estimate 0.75
            for subj in weights:
                if subj in strong and subj not in subject_accuracy:
                    subject_accuracy[subj] = 0.75
        for weak in learner_profile.get("weaknesses", []):
            for subj in weights:
                if subj in weak and subj not in subject_accuracy:
                    subject_accuracy[subj] = 0.40

    if subject_accuracy:
        total_weight = 0.0
        weighted_sum = 0.0
        for subject, weight in weights.items():
            acc = subject_accuracy.get(subject)
            if acc is not None:
                weighted_sum += weight * acc
                total_weight += weight
        if total_weight > 0:
            return min(1.0, max(0.0, weighted_sum / total_weight))

    # Priority 4: cold start from elective subjects
    elective = profile.get("elective_subjects", [])
    if elective:
        CORE_SUBJECTS = {"语文", "数学", "英语"}
        elective_set = set(elective)
        total_weight = 0.0
        weighted_sum = 0.0
        for subject, weight in weights.items():
            if subject in CORE_SUBJECTS:
                est = 0.65
            else:
                est = 0.65 if subject in elective_set else 0.40
            weighted_sum += weight * est
            total_weight += weight
        if total_weight > 0:
            return min(1.0, max(0.0, weighted_sum / total_weight))

    return 0.5


def _explain_dorm(score: float) -> str:
    if score >= 8:
        return "宿舍条件优秀（4人间以内，空调+独立卫浴）"
    elif score >= 5:
        return "宿舍条件良好"
    else:
        return "宿舍条件一般"


def _explain_city(score: float) -> str:
    if score >= 8:
        return "城市经济发达，实习和就业机会丰富"
    elif score >= 5:
        return "城市发展较好"
    else:
        return "城市发展一般"


def _explain_cost(idx: float) -> str:
    if idx <= 0.8:
        return "生活成本较低，性价比高"
    elif idx <= 1.2:
        return "生活成本适中"
    else:
        return "生活成本较高"


def _explain_employment(rate: float) -> str:
    if rate >= 0.9:
        return "就业率很高"
    elif rate >= 0.8:
        return "就业率良好"
    else:
        return "就业率一般"


def _explain_admission(prob: float) -> str:
    if prob >= 0.7:
        return "录取概率较高，建议作为保底志愿"
    elif prob >= 0.4:
        return "录取概率中等，建议作为稳妥志愿"
    else:
        return "录取概率较低，建议作为冲刺志愿"


def _explain_academic_fit(fit: float) -> str:
    if fit >= 0.7:
        return "与学习画像高度匹配"
    elif fit >= 0.4:
        return "与学习画像部分匹配"
    else:
        return "与学习画像匹配度较低"


def _explain_bargain(score: float) -> str:
    if score >= 0.6:
        return "该校近年位次波动较大，可能有捡漏机会"
    elif score >= 0.3:
        return "该校位次有轻微波动"
    else:
        return "该校位次较稳定，捡漏机会较小"


def _compute_rank_prob(
    user_rank: int, group_ranks: dict[int, int],
    year_weights: dict[int, float] | None = None,
) -> tuple[float, dict[str, Any]]:
    if not group_ranks:
        return 0.5, {"reason": "无录取位次数据"}
    if year_weights is None:
        year_weights = {2025: 0.5, 2024: 0.35, 2023: 0.15}
    total_weight = 0.0
    weighted_avg_rank = 0.0
    years_used: dict[str, Any] = {}
    for yr, rk in sorted(group_ranks.items(), key=lambda x: -x[0]):
        w = year_weights.get(yr, 0.1)
        if rk > 0:
            total_weight += w
            weighted_avg_rank += rk * w
            years_used[str(yr)] = {"min_rank": rk, "weight": w}
    if total_weight <= 0:
        return 0.5, {"reason": "位次数据权重为零"}
    weighted_avg_rank /= total_weight

    if user_rank <= weighted_avg_rank:
        prob = 0.5 + 0.5 * (weighted_avg_rank - user_rank) / weighted_avg_rank
    else:
        prob = 0.5 * weighted_avg_rank / user_rank
    prob = max(0.05, min(0.95, prob))

    return prob, {
        "weighted_avg_rank": round(weighted_avg_rank),
        "user_rank": user_rank,
        "years_used": years_used,
    }


def score_group(
    college: dict[str, Any],
    group_code: str,
    majors_data: list[dict[str, Any]],
    user_profile: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
    group_prob: float = 0.5,
    precomputed_major_probs: dict[str, float] | None = None,
    precomputed_major_evidences: dict[str, dict] | None = None,
    strategy: str | list[str] | None = None,
) -> dict[str, Any]:
    user_profile = user_profile or {}
    w = _resolve_strategy_weights(weights, strategy or "default")

    college_dorm = float(college.get("dorm_score", 0) or 0)
    dorm_quality = _normalize(college_dorm, 0, 10)

    city_vitality_val = float(college.get("city_vitality", 0) or 0)
    city_vitality = _normalize(city_vitality_val, 0, 10)

    cost_idx = float(college.get("cost_index", 1) or 1)
    cost_efficiency = _normalize(1.0 / max(cost_idx, 0.1), 0.5, 2.0)

    emp_rate = float(college.get("employment_rate", 0) or 0)
    employment = _normalize(emp_rate, 0, 1)

    admission_prob = group_prob

    major_fits: list[float] = []
    scored_majors: list[dict[str, Any]] = []
    for m in majors_data:
        mid = m.get("major_id", "")
        fit = _calc_academic_fit({"id": mid, "major_id": mid}, user_profile)
        major_fits.append(fit)
        major_prob = (precomputed_major_probs or {}).get(mid, group_prob)
        ev = (precomputed_major_evidences or {}).get(mid, {})
        sort_score = major_prob * 0.6 + fit * 0.4
        scored_majors.append({
            "major_id": mid,
            "major_name": m.get("major_name", ""),
            "admission_prob": major_prob,
            "sort_score": sort_score,
            "evidence": ev,
            "min_rank": m.get("min_rank", 0),
        })

    scored_majors.sort(key=lambda x: -x["sort_score"])

    TAGS = ["推荐", "优选", "可选"]
    for i, sm in enumerate(scored_majors):
        if i == 0:
            sm["tag"] = TAGS[0] if sm["admission_prob"] > 0.8 else TAGS[1] if sm["admission_prob"] >= 0.45 else TAGS[2]
        else:
            sm["tag"] = TAGS[2]

    academic_fit_val = max(major_fits) if major_fits else 0.5

    detail = {
        "admission_prob": group_prob,
        "dorm_quality": round(dorm_quality, 4),
        "city_vitality": round(city_vitality, 4),
        "cost_efficiency": round(cost_efficiency, 4),
        "employment": round(employment, 4),
        "academic_fit": round(academic_fit_val, 4),
        "majors_count": len(scored_majors),
    }

    total_score = (
        dorm_quality * w.get("dorm_quality", 0) +
        city_vitality * w.get("city_vitality", 0) +
        cost_efficiency * w.get("cost_efficiency", 0) +
        employment * w.get("employment", 0) +
        admission_prob * w.get("admission_prob", 0) +
        academic_fit_val * w.get("academic_fit", 0)
    )

    return {
        "group_code": group_code,
        "group_prob": group_prob,
        "total_score": round(total_score, 4),
        "majors": scored_majors,
        "detail_scores": detail,
    }


def generate_group_recommendations(
    colleges_map: dict[str, dict[str, Any]],
    province: str,
    exam_category: str,
    user_profile: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
    top_n: int = 100,
    strategy: str | list[str] | None = None,
    major_categories: list[str] | None = None,
    score_rank_range: tuple[int, int] | None = None,
    per_tier_caps: dict[str, int] | None = None,
) -> dict[str, Any]:
    from deeptutor.services.custom.db import get_connection
    from deeptutor.services.custom.admission_dao import score_to_rank

    user_profile = user_profile or {}
    user_rank = user_profile.get("rank", 0) or 0

    if "_subjects" not in user_profile:
        try:
            from deeptutor.services.custom.study_dao import get_subject_summary
            uid = user_profile.get("user_id") or "default"
            subjects = get_subject_summary(uid)
            if subjects:
                user_profile = {**user_profile, "_subjects": subjects}
        except Exception:
            pass

    conn = get_connection()

    major_category_ids: set[str] | None = None
    if major_categories:
        placeholders = ",".join("?" * len(major_categories))
        major_category_ids = {
            r["id"] for r in conn.execute(
                f"SELECT id FROM majors WHERE category IN ({placeholders})",
                major_categories,
            ).fetchall()
        }

    rank_low = 0
    if score_rank_range:
        rank_low, _ = score_rank_range
    elif user_profile.get("score") and user_rank:
        rank_low = score_to_rank(province, 2025, exam_category, min(750, int(user_profile["score"]) + 50)) or 0

    year_weights = {2025: 0.5, 2024: 0.35, 2023: 0.15}

    rank_clause = ""
    rank_params: list[int] = []
    if rank_low > 0:
        rank_clause = "AND EXISTS (SELECT 1 FROM admission_ranks ar2 WHERE ar2.college_id=ar.college_id AND ar2.group_code=ar.group_code AND ar2.province=ar.province AND ar2.year=ar.year AND ar2.min_rank >= ?)"
        rank_params = [rank_low]

    group_years = conn.execute(
        f"""SELECT college_id, group_code, year, MIN(min_rank) as best_rank
           FROM admission_ranks ar
           WHERE province=? AND exam_category=? AND group_code!='' AND min_rank > 0 {rank_clause}
           GROUP BY college_id, group_code, year
           ORDER BY college_id, group_code, year DESC""",
        (province, exam_category, *rank_params),
    ).fetchall()

    major_ranks = conn.execute(
        f"""SELECT ar.college_id, ar.group_code, ar.major_id, MIN(ar.min_rank) as best_rank,
                  COALESCE(m.name, '') as major_name
           FROM admission_ranks ar
           LEFT JOIN majors m ON ar.major_id = m.id
           WHERE ar.province=? AND ar.exam_category=? AND ar.group_code!='' AND ar.major_id!='GEN' AND ar.min_rank > 0 {rank_clause}
           GROUP BY ar.college_id, ar.group_code, ar.major_id
           ORDER BY ar.college_id, ar.group_code, ar.major_id""",
        (province, exam_category, *rank_params),
    ).fetchall()
    conn.close()

    group_agg: dict[tuple[str, str], dict[int, int]] = defaultdict(dict)
    for r in group_years:
        key = (r["college_id"], r["group_code"])
        group_agg[key][int(r["year"])] = int(r["best_rank"])

    majors_per_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    major_best_ranks: dict[tuple[str, str, str], int] = {}
    for r in major_ranks:
        key = (r["college_id"], r["group_code"])
        mid = r["major_id"]
        if major_category_ids and mid not in major_category_ids:
            continue
        rk = int(r["best_rank"])
        majors_per_group[key].append({"major_id": mid, "min_rank": rk, "major_name": r["major_name"] or ""})
        major_best_ranks[(r["college_id"], r["group_code"], mid)] = rk

    valid_groups: set[tuple[str, str]] = set(majors_per_group.keys())
    if major_category_ids:
        group_agg = {k: v for k, v in group_agg.items() if k in valid_groups}

    all_groups: list[dict[str, Any]] = []
    for (cid, gc), group_ranks in group_agg.items():
        college = colleges_map.get(cid)
        if not college:
            continue
        group_prob, _ = _compute_rank_prob(user_rank, group_ranks, year_weights)

        majors_data = majors_per_group.get((cid, gc), [])
        precomputed_major_probs: dict[str, float] = {}
        precomputed_major_evidences: dict[str, dict] = {}
        for m in majors_data:
            mid = m["major_id"]
            major_rank = major_best_ranks.get((cid, gc, mid), 0)
            if major_rank and major_rank > 0:
                if user_rank <= major_rank:
                    major_prob = 0.5 + 0.5 * (major_rank - user_rank) / major_rank
                else:
                    major_prob = 0.5 * major_rank / user_rank
                major_prob = max(0.05, min(0.95, major_prob))
            else:
                major_prob = group_prob
            precomputed_major_probs[mid] = major_prob
            precomputed_major_evidences[mid] = {"major_best_rank": major_rank} if major_rank > 0 else {}

        result = score_group(
            college, gc, majors_data, user_profile, weights,
            group_prob=group_prob,
            precomputed_major_probs=precomputed_major_probs,
            precomputed_major_evidences=precomputed_major_evidences,
            strategy=strategy,
        )
        result["college"] = college
        bargain = _calc_bargain_score(cid, user_profile)
        result["bargain_score"] = round(bargain, 4)
        all_groups.append(result)

    safe, steady, reach = [], [], []
    for g in all_groups:
        prob = g["group_prob"]
        if prob >= 0.65:
            safe.append(g)
        elif prob >= 0.35:
            steady.append(g)
        else:
            reach.append(g)

    for lst in (safe, steady, reach):
        lst.sort(key=lambda x: -x["total_score"])

    if per_tier_caps:
        selected = {
            "safe": safe[:per_tier_caps.get("safe", 80)],
            "steady": steady[:per_tier_caps.get("steady", 100)],
            "reach": reach[:per_tier_caps.get("reach", 50)],
        }
    else:
        per_tier = max(1, top_n // 3)
        selected = {
            "safe": safe[:per_tier],
            "steady": steady[:per_tier],
            "reach": reach[:per_tier],
        }

    return {"tiers": selected, "total": len(all_groups)}
