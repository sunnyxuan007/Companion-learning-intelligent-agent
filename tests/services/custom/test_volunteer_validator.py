from __future__ import annotations

import pytest

from deeptutor.services.custom.student_profile import StudentProfile
from deeptutor.services.custom.volunteer_validator import (
    validate_all,
    _check_gender,
    _check_medical,
    _check_subject,
)


class TestCheckMedical:
    def test_no_restrictions(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理")
        result = _check_medical(profile, {"id": "EN001", "name": "计算机"})
        assert result == []

    def test_no_major(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", medical_restrictions=["101"])
        result = _check_medical(profile, None)
        assert result == []

    def test_affected_major(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", medical_restrictions=["101"])
        result = _check_medical(profile, {"id": "SC003", "name": "化学"})
        assert len(result) == 1
        assert result[0]["type"] == "medical"
        assert result[0]["severity"] == "error"

    def test_unaffected_major(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", medical_restrictions=["301"])
        result = _check_medical(profile, {"id": "EN001", "name": "计算机"})
        assert result == []

    def test_monitor_color_affects_cs(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", medical_restrictions=["104"])
        result = _check_medical(profile, {"id": "EN001", "name": "计算机科学与技术"})
        assert len(result) == 1

    def test_strabismus_affects_medicine(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", medical_restrictions=["306"])
        result = _check_medical(profile, {"id": "MD001", "name": "临床医学"})
        assert len(result) == 1


class TestCheckSubject:
    def test_no_requirement(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理")
        result = _check_subject(profile, {"id": "EN001", "name": "计算机"})
        assert result == []

    def test_matching(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理")
        result = _check_subject(profile, {"id": "EN001", "name": "计算机", "subject_group": "物理"})
        assert result == []

    def test_not_matching(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理")
        result = _check_subject(profile, {"id": "EN001", "name": "英语", "subject_group": "历史"})
        assert len(result) == 1
        assert result[0]["type"] == "subject"


class TestCheckGender:
    def test_no_restriction(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", gender="男")
        result = _check_gender(profile, {}, None)
        assert result == []

    def test_male_only_male_ok(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", gender="男")
        result = _check_gender(profile, {"gender_restriction": "male_only"}, None)
        assert result == []

    def test_male_only_female_blocked(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", gender="女")
        result = _check_gender(profile, {"gender_restriction": "male_only"}, None)
        assert len(result) == 1
        assert result[0]["type"] == "gender"
        assert result[0]["severity"] == "error"

    def test_female_only_male_blocked(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", gender="男")
        result = _check_gender(profile, {"gender_restriction": "female_only"}, None)
        assert len(result) == 1

    def test_major_gender_restriction(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", gender="女")
        result = _check_gender(profile, {}, {"id": "M001", "gender_restriction": "male_only"})
        assert len(result) == 1


class TestValidateAll:
    def test_clean_profile(self):
        profile = StudentProfile(province="广东", year=2026, exam_category="物理", rank=5000)
        result = validate_all(profile, {"id": "C001", "name": "测试大学"}, {"id": "EN001"})
        assert result == []

    def test_multiple_violations(self):
        profile = StudentProfile(
            province="广东", year=2026, exam_category="物理",
            medical_restrictions=["101"], gender="女",
            rank=5000,
        )
        college = {"id": "C001", "name": "测试大学", "gender_restriction": "male_only"}
        major = {"id": "SC003", "name": "化学"}
        result = validate_all(profile, college, major)
        types = {v["type"] for v in result}
        assert "medical" in types
        assert "gender" in types
