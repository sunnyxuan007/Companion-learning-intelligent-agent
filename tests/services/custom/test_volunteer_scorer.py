from __future__ import annotations

import math

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.volunteer_scorer import (
    _calc_admission_prob,
    _normalize,
    _split_tiers,
    generate_group_recommendations,
    generate_recommendations,
    score_college_major,
)


class TestNormalize:
    def test_at_min(self) -> None:
        assert _normalize(0, 0, 100) == 0.0

    def test_at_max(self) -> None:
        assert _normalize(100, 0, 100) == 1.0

    def test_midpoint(self) -> None:
        assert _normalize(50, 0, 100) == 0.5

    def test_below_min(self) -> None:
        assert _normalize(-10, 0, 100) == 0.0

    def test_above_max(self) -> None:
        assert _normalize(200, 0, 100) == 1.0

    def test_equal_min_max(self) -> None:
        assert _normalize(50, 100, 100) == 0.5


class TestCalcAdmissionProb:
    def test_no_rank_returns_half(self) -> None:
        major: dict = {}
        profile: dict = {}
        prob, _ = _calc_admission_prob(major, profile)
        assert prob == 0.5

    def test_rank_below_average(self) -> None:
        major = {"min_rank_2024": 1000, "min_rank_2023": 1200, "min_rank_2022": 1100}
        profile = {"rank": 500, "province": "广东", "exam_category": "物理"}
        prob, evidence = _calc_admission_prob(major, profile)
        assert prob > 0.5  # user rank better than college historical avg
        assert "confidence" in evidence

    def test_rank_above_average(self) -> None:
        major = {"min_rank_2024": 1000, "min_rank_2023": 1200, "min_rank_2022": 1100}
        profile = {"rank": 3000, "province": "广东", "exam_category": "物理"}
        prob, _ = _calc_admission_prob(major, profile)
        assert prob < 0.5  # user rank worse than college historical avg

    def test_some_years_missing(self) -> None:
        major: dict = {"min_rank_2024": 1000}
        profile: dict = {"rank": 500, "province": "广东", "exam_category": "物理"}
        prob, _ = _calc_admission_prob(major, profile)
        assert prob > 0.5

    def test_target_year_excluded(self) -> None:
        # 目标年 2026：min_rank_2026 是当年结果，不得参与预测（AGENTS.md Phase 23.2）
        major: dict = {"min_rank_2026": 500, "min_rank_2024": 1000}
        profile: dict = {"rank": 2000, "province": "广东", "exam_category": "物理"}
        prob, evidence = _calc_admission_prob(major, profile)
        assert prob < 0.5  # 若 2026 混入，平均位次会被拉低到 500 附近 -> prob 会 >0.5
        assert "2026" not in (evidence.get("years_used") or {})


class TestComputeRankProbWeights:
    def test_recent_year_dominates(self) -> None:
        from deeptutor.services.custom.volunteer_scorer import _compute_rank_prob
        # 2025 位次 1000（去年，权重0.7），2024 位次 100000（0.2），2023 位次 100000（0.1）
        prob, ev = _compute_rank_prob(2000, {2025: 1000, 2024: 100000, 2023: 100000})
        assert prob > 0.5
        assert abs(ev["weighted_avg_rank"] - 30700) < 200  # 0.7*1000+0.2*100000+0.1*100000

    def test_target_year_ignored_in_weights(self) -> None:
        from deeptutor.services.custom.volunteer_scorer import _compute_rank_prob
        # 2026 行权重为 0.1（未知年兜底），但预测时应由调用方排除目标年
        prob, ev = _compute_rank_prob(2000, {2026: 1000, 2025: 5000})
        # (0.1*1000 + 0.7*5000) / 0.8 = 4500
        assert ev["weighted_avg_rank"] == 4500
        assert prob > 0.5


class TestCalcAdmissionProbProvince:
    def test_province_rank_uses_admission_table(self, custom_db: None) -> None:
        major = {"id": "M001", "major_id": "M001"}
        profile = {"rank": 30, "province": "广东", "exam_category": "物理"}
        prob, evidence = _calc_admission_prob(major, profile, college_id="C001")
        assert prob > 0.6
        assert evidence.get("num_years", 0) > 0

    def test_province_rank_no_data_falls_back(self, custom_db: None) -> None:
        major = {"id": "M001", "min_rank_2024": 1000}
        profile = {"rank": 500, "province": "北京", "exam_category": "物理"}
        prob, _ = _calc_admission_prob(major, profile, college_id="C001")
        assert prob > 0.5


class TestEvidenceAndBargain:
    def test_evidence_in_score_result(self) -> None:
        college = {"id": "C001", "dorm_score": 8.0, "city_vitality": 9.0, "cost_index": 4.0, "employment_rate": 0.95, "avg_salary": 20000}
        major = {"min_rank_2024": 50, "min_rank_2023": 55, "min_rank_2022": 60}
        profile = {"rank": 30, "province": "广东", "exam_category": "物理"}
        result = score_college_major(college, major, profile)
        assert "evidence" in result
        assert "admission_confidence" in result["evidence"]
        assert "bargain_score" in result["evidence"]


class TestScoreCollegeMajor:
    def test_full_scoring(self) -> None:
        college = {"dorm_score": 8.0, "city_vitality": 9.0, "cost_index": 4.0, "employment_rate": 0.95, "avg_salary": 20000}
        major = {"min_rank_2024": 50, "min_rank_2023": 55, "min_rank_2022": 60}
        profile = {"rank": 30}
        result = score_college_major(college, major, profile)
        assert "total_score" in result
        assert "detail_scores" in result
        assert "explanations" in result
        assert 0 <= result["total_score"] <= 1

    def test_no_major(self) -> None:
        college = {"dorm_score": 8.0, "city_vitality": 9.0, "cost_index": 4.0, "employment_rate": 0.95, "avg_salary": 20000}
        result = score_college_major(college, major=None, user_profile=None)
        assert result["detail_scores"]["admission_prob"] == 0.5  # college-level fallback
        assert result["detail_scores"]["academic_fit"] == 0.5  # default when no major

    def test_custom_weights(self) -> None:
        college = {"dorm_score": 8.0, "city_vitality": 9.0, "cost_index": 4.0, "employment_rate": 0.95, "avg_salary": 20000}
        major = {"min_rank_2024": 50, "min_rank_2023": 55, "min_rank_2022": 60}
        profile = {"rank": 30}
        weights = {"dorm_quality": 1.0, "city_vitality": 0, "cost_efficiency": 0, "employment": 0, "admission_prob": 0, "academic_fit": 0, "career_alignment": 0}
        result = score_college_major(college, major, profile, weights)
        assert result["detail_scores"]["dorm_quality"] > 0
        assert result["detail_scores"]["city_vitality"] > 0  # raw value, unaffected by weight
        assert result["detail_scores"]["admission_prob"] > 0  # raw value, unaffected by weight
        # total_score should only reflect dorm_quality (weight=1.0)
        expected = round(result["detail_scores"]["dorm_quality"], 4)
        assert abs(result["total_score"] - expected) < 0.001


class TestGenerateRecommendations:
    def test_sorts_by_score(self, custom_db: None) -> None:
        colleges = [
            {"id": "C001", "name": "清华", "dorm_score": 9, "city_vitality": 9, "cost_index": 3, "employment_rate": 0.98, "avg_salary": 25000},
            {"id": "C005", "name": "广工", "dorm_score": 6, "city_vitality": 6.5, "cost_index": 6, "employment_rate": 0.88, "avg_salary": 15000},
        ]
        result = generate_recommendations(colleges, user_profile={"rank": 100})
        recs = result["recommendations"]
        assert recs[0]["total_score"] >= recs[-1]["total_score"]

    def test_empty_colleges(self) -> None:
        result = generate_recommendations([], user_profile=None)
        assert result["recommendations"] == []
        assert result["tiers"]["reach"] == []
        assert result["tiers"]["steady"] == []
        assert result["tiers"]["safe"] == []


class TestSplitTiers:
    def test_safe_threshold(self) -> None:
        items = [
            {"detail_scores": {"admission_prob": 0.85}},
            {"detail_scores": {"admission_prob": 0.75}},
            {"detail_scores": {"admission_prob": 0.5}},
            {"detail_scores": {"admission_prob": 0.4}},
        ]
        safe, steady, reach = _split_tiers(items)
        assert len(safe) == 1  # prob >= 0.8
        assert len(steady) == 2  # 0.45 <= prob < 0.8
        assert len(reach) == 1  # prob < 0.45


class TestGroupRecommendationsMedicalFilter:
    def _seed_group_data(self) -> None:
        conn = get_connection()
        now = 1787210000.0
        # C001 清华 两个组：g201 化学(不招色盲色弱) + 计算机(无限制)；g202 临床医学(不招色盲色弱)
        # C003 深大 g201 心理学(请色盲色弱慎重报考 软提醒)
        for college, gc, mid, major_name, note, rank in [
            ("C001", "201", "A1", "化学", "不招色盲色弱", 30000),
            ("C001", "201", "A2", "计算机科学与技术", "", 32000),
            ("C001", "202", "B1", "临床医学", "不招色盲色弱", 35000),
            ("C003", "201", "C1", "心理学", "请色盲色弱的考生慎重报考", 80000),
        ]:
            conn.execute(
                """INSERT OR REPLACE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (college, mid, "广东", 2025, "本科批", rank, 0, 0, "物理", gc),
            )
            conn.execute(
                """INSERT OR REPLACE INTO college_major_name
                   (college_id, major_id, major_name, medical_note) VALUES (?,?,?,?)""",
                (college, mid, major_name, note),
            )
        conn.commit()
        conn.close()

    def _colleges_map(self) -> dict:
        base = {
            "dorm_score": 7.0, "city_vitality": 8.0, "cost_index": 1.0,
            "employment_rate": 0.9, "avg_salary": 20000,
        }
        return {
            "C001": {"id": "C001", "name": "清华大学", "province": "北京", **base},
            "C003": {"id": "C003", "name": "深圳大学", "province": "广东", **base},
        }

    def test_medical_removes_matching_majors(self, custom_db: None) -> None:
        self._seed_group_data()
        result = generate_group_recommendations(
            self._colleges_map(), "广东", "物理",
            user_profile={"rank": 5000, "medical_restrictions": ["101"]},
            top_n=100, batch="本科批",
        )
        tiers = result["tiers"]
        all_groups = tiers["safe"] + tiers["steady"] + tiers["reach"]
        # 用户色弱(101)：g201 化学剔除、保留计算机；g202 临床医学全部剔除 → 组移除
        ids = {(g["college"]["id"], g.get("group_code")) for g in all_groups}
        assert ("C001", "201") in ids
        assert ("C001", "202") not in ids
        g201 = next(g for g in all_groups if (g["college"]["id"], g.get("group_code")) == ("C001", "201"))
        majors = {m["major_id"]: m for m in g201["majors"]}
        assert "A1" not in majors  # 化学被剔除
        assert "A2" in majors      # 计算机保留
        assert result["medical_filtered"]["majors"] >= 2
        assert result["medical_filtered"]["groups"] >= 1

    def test_medical_keeps_other_restrictions(self, custom_db: None) -> None:
        self._seed_group_data()
        # 用户只勾选单色识别(103)：g201 化学/计算机无 103 限制 → 全保留；深大心理学保留
        result = generate_group_recommendations(
            self._colleges_map(), "广东", "物理",
            user_profile={"rank": 5000, "medical_restrictions": ["103"]},
            top_n=100, batch="本科批",
        )
        tiers = result["tiers"]
        all_groups = tiers["safe"] + tiers["steady"] + tiers["reach"]
        ids = {(g["college"]["id"], g.get("group_code")) for g in all_groups}
        assert ("C001", "201") in ids
        assert ("C001", "202") in ids
        g202 = next(g for g in all_groups if (g["college"]["id"], g.get("group_code")) == ("C001", "202"))
        assert any(m["major_id"] == "B1" for m in g202["majors"])

    def test_no_restrictions_no_filter(self, custom_db: None) -> None:
        self._seed_group_data()
        result = generate_group_recommendations(
            self._colleges_map(), "广东", "物理",
            user_profile={"rank": 5000},
            top_n=100, batch="本科批",
        )
        assert "medical_filtered" not in result
        tiers = result["tiers"]
        all_groups = tiers["safe"] + tiers["steady"] + tiers["reach"]
        g202 = next(g for g in all_groups if (g["college"]["id"], g.get("group_code")) == ("C001", "202"))
        assert any(m["major_id"] == "B1" for m in g202["majors"])

    def test_target_year_rows_excluded(self, custom_db: None) -> None:
        """目标年(2026)的投档位次不得参与预测：仅 2026 数据的组不出现。"""
        conn = get_connection()
        # C001 g201: 2025 位次 30000 + 2026 位次 100（目标年，应被忽略）
        # C003 g301: 仅 2026 位次 5000（无历史 → 不出现）
        for college, gc, year, rank in [
            ("C001", "201", 2025, 30000),
            ("C001", "201", 2026, 100),
            ("C003", "301", 2026, 5000),
        ]:
            conn.execute(
                """INSERT OR REPLACE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code)
                   VALUES (?, 'GEN', '广东', ?, '本科批', ?, 0, 0, '物理', ?)""",
                (college, year, rank, gc),
            )
        conn.commit()
        conn.close()

        result = generate_group_recommendations(
            self._colleges_map(), "广东", "物理",
            user_profile={"rank": 5000},
            top_n=100, batch="本科批",
        )
        tiers = result["tiers"]
        all_groups = tiers["safe"] + tiers["steady"] + tiers["reach"]
        ids = {(g["college"]["id"], g.get("group_code")) for g in all_groups}
        assert ("C001", "201") in ids     # 有 2025 历史 → 保留
        assert ("C003", "301") not in ids  # 仅目标年数据 → 不出现
