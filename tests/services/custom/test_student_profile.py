from __future__ import annotations

from deeptutor.services.custom.student_profile import (
    RESTRICTION_AFFECTED_MAJORS,
    StudentProfile,
    get_affected_major_ids,
)


class TestStudentProfileValidation:
    def test_valid_profile(self):
        p = StudentProfile(province="广东", year=2026, exam_category="物理", rank=5000)
        assert p.validate() == []

    def test_missing_province(self):
        p = StudentProfile(province="", year=2026, exam_category="物理")
        assert "省份不能为空" in p.validate()

    def test_invalid_year(self):
        p = StudentProfile(province="广东", year=2019, exam_category="物理")
        assert "年份无效" in p.validate()

    def test_invalid_exam_category(self):
        p = StudentProfile(province="广东", year=2026, exam_category="文科")
        assert "首选科目必须是物理或历史" in p.validate()

    def test_missing_score_and_rank(self):
        p = StudentProfile(province="广东", year=2026, exam_category="物理")
        assert "分数和位次不能同时为空" in p.validate()

    def test_negative_score(self):
        p = StudentProfile(province="广东", year=2026, exam_category="物理", score=-10)
        assert "分数不能为负数" in p.validate()

    def test_invalid_rank(self):
        p = StudentProfile(province="广东", year=2026, exam_category="物理", rank=0)
        assert "位次不能小于1" in p.validate()

    def test_with_score_only(self):
        p = StudentProfile(province="广东", year=2026, exam_category="物理", score=600)
        assert p.validate() == []

    def test_with_rank_only(self):
        p = StudentProfile(province="广东", year=2026, exam_category="物理", rank=5000)
        assert p.validate() == []


class TestStudentProfileConversion:
    def test_to_dict(self):
        p = StudentProfile(
            province="广东", year=2026, exam_category="物理",
            elective_subjects=["化学", "生物"], rank=5000, gender="男",
            medical_restrictions=["101", "201"],
        )
        d = p.to_dict()
        assert d["province"] == "广东"
        assert d["rank"] == 5000
        assert d["medical_restrictions"] == ["101", "201"]
        assert "preferences" not in d

    def test_to_dict_with_preferences(self):
        p = StudentProfile(
            province="广东", year=2026, exam_category="物理",
            preferences={"level": "985", "city_rank": "一线"},
        )
        d = p.to_dict()
        assert d["preferences"] == {"level": "985", "city_rank": "一线"}

    def test_from_dict(self):
        d = {
            "province": "广东", "year": 2026, "exam_category": "物理",
            "rank": 3000, "score": 600, "medical_restrictions": ["101"],
        }
        p = StudentProfile.from_dict(d)
        assert p.province == "广东"
        assert p.rank == 3000
        assert p.score == 600
        assert p.medical_restrictions == ["101"]
        assert p.elective_subjects == []

    def test_from_dict_minimal(self):
        p = StudentProfile.from_dict({"province": "广东", "year": 2026, "exam_category": "物理"})
        assert p.score is None
        assert p.rank is None
        assert p.medical_restrictions == []
        assert p.gender is None


class TestMedicalRestrictionMap:
    def test_get_affected_majors(self):
        affected = get_affected_major_ids(["101"])
        assert "EN001" in affected
        assert "MD001" in affected
        assert "BS005" not in affected

    def test_get_affected_majors_multiple(self):
        affected = get_affected_major_ids(["101", "301"])
        assert "EN001" in affected
        assert "BS005" in affected

    def test_get_affected_majors_empty(self):
        affected = get_affected_major_ids([])
        assert len(affected) == 0

    def test_get_affected_majors_no_match(self):
        affected = get_affected_major_ids(["999"])
        assert len(affected) == 0

    def test_restriction_map_has_keys(self):
        assert "101" in RESTRICTION_AFFECTED_MAJORS
        assert "501" in RESTRICTION_AFFECTED_MAJORS
