from __future__ import annotations

import math
from typing import Any

from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS
from deeptutor.services.custom.study_dao import get_subject_summary

SUBJECT_CATEGORIES: dict[str, list[str]] = {
    "stem": ["数学", "物理", "化学", "生物", "信息技术"],
    "liberal": ["语文", "英语", "政治", "历史", "地理"],
    "art": ["美术", "音乐"],
}


def compute_adaptive_weights(
    user_id: str,
    base_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    base = base_weights or dict(VOLUNTEER_DEFAULT_WEIGHTS)

    subjects = get_subject_summary(user_id)
    if not subjects:
        return base

    total_records = sum(s.get("count", 0) for s in subjects)
    unique_subjects = len(subjects)

    if total_records < 10 or unique_subjects < 2:
        return base

    data_confidence = min(1.0, total_records / 50.0) * min(1.0, unique_subjects / 4.0)

    subject_accuracy: dict[str, float] = {}
    subject_count: dict[str, int] = {}
    for s in subjects:
        name = str(s.get("subject", ""))
        acc = s.get("avg_accuracy")
        cnt = s.get("count", 0)
        if name and acc is not None:
            subject_accuracy[name] = float(acc)
            subject_count[name] = int(cnt)

    if not subject_accuracy:
        return base

    cats = _compute_category_scores(subject_accuracy, subject_count)

    delta = _compute_delta(base, cats, data_confidence)
    adjusted = {}
    for k in base:
        adjusted[k] = max(0.01, base[k] + delta.get(k, 0.0))

    total = sum(adjusted.values())
    if total > 0:
        for k in adjusted:
            adjusted[k] = round(adjusted[k] / total, 4)

    _renormalize(adjusted)
    return adjusted


def _compute_category_scores(
    accuracy: dict[str, float],
    counts: dict[str, int],
) -> dict[str, float]:
    cat_scores: dict[str, float] = {}
    for cat, subjects in SUBJECT_CATEGORIES.items():
        scores = [accuracy[s] for s in subjects if s in accuracy]
        if scores:
            cat_scores[cat] = sum(scores) / len(scores)
    if not cat_scores:
        return {"stem": 0.5, "liberal": 0.5, "art": 0.5}

    scores = list(cat_scores.values())
    if len(scores) < 2:
        return {"stem": scores[0], "liberal": scores[0], "art": scores[0]}

    return cat_scores


def _compute_delta(
    base: dict[str, float],
    cats: dict[str, float],
    confidence: float,
) -> dict[str, float]:
    stem = cats.get("stem", 0.5)
    liberal = cats.get("liberal", 0.5)
    art = cats.get("art", 0.5)
    all_avg = (stem + liberal + art) / 3.0
    spread = max(0.0, max(stem, liberal, art) - min(stem, liberal, art))

    delta: dict[str, float] = {}

    if spread > 0.15:
        stem_advantage = stem - all_avg
        delta["academic_fit"] = 0.08 * stem_advantage * confidence
        if stem_advantage > 0:
            delta["employment"] = 0.04 * stem_advantage * confidence
    else:
        delta["academic_fit"] = 0.03 * confidence

    strong_liberal = liberal > 0.7 and liberal > stem
    if strong_liberal:
        delta["career_alignment"] = 0.04 * (liberal - stem) * confidence

    if spread < 0.1:
        delta["admission_prob"] = 0.03 * confidence

    delta["dorm_quality"] = -0.02 * confidence
    delta["city_vitality"] = -0.02 * confidence

    sum_pos = sum(v for v in delta.values() if v > 0)
    sum_neg = abs(sum(v for v in delta.values() if v < 0))

    for k in list(delta.keys()):
        total_k_weight = base.get(k, 0.1)
        max_increase = total_k_weight * 0.5
        max_decrease = total_k_weight * 0.4
        delta[k] = max(-max_decrease, min(max_increase, delta[k]))

    return delta


def _renormalize(weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        for k in weights:
            weights[k] = round(weights[k] / total, 4)
    leftover = 1.0 - sum(weights.values())
    if abs(leftover) > 0.0001:
        max_key = max(weights, key=weights.get)
        weights[max_key] = round(weights[max_key] + leftover, 4)
