from __future__ import annotations

import math

from deeptutor.services.custom.volunteer_scorer import (
    _calc_admission_prob,
    _normalize,
    _split_tiers,
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
