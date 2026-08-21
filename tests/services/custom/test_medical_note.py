from __future__ import annotations

from deeptutor.services.custom.medical_dao import (
    classify_medical_note,
    extract_medical_clause,
    major_medical_status,
)


class TestExtractMedicalClause:
    def test_hard_color(self):
        assert extract_medical_clause("(不招色盲色弱)(校本部)") == "不招色盲色弱"

    def test_hard_multi(self):
        assert extract_medical_clause("(不招色盲色弱，不招单色识别不全者)(校本部)") == "不招色盲色弱；不招单色识别不全者"

    def test_single_color(self):
        assert extract_medical_clause("(不招单色识别不全者)(校本部)") == "不招单色识别不全者"

    def test_soft(self):
        assert extract_medical_clause("(因用人单位可能对考生身体素质有要求，请色盲色弱的考生慎重报考)(校本部)") == "请色盲色弱的考生慎重报考"

    def test_campus_only(self):
        assert extract_medical_clause("(龙湖东校区)") == ""

    def test_campus_and_medical(self):
        assert extract_medical_clause("(5年)(不招色盲)(主校区)") == "不招色盲"

    def test_police_note(self):
        assert extract_medical_clause("(面向地方公安机关入警就业)(只招男生；裸眼视力≥4.8，不招色盲色弱，政审、面试合格)(校本部)") == "裸眼视力≥4.8；不招色盲色弱"


class TestClassifyMedicalNote:
    def test_color_weak_and_blind(self):
        cls = classify_medical_note("不招色盲色弱")
        assert cls["hard"] == {"101", "102"}
        assert cls["soft"] == {"101", "102"}

    def test_color_blind_only(self):
        cls = classify_medical_note("不招色盲")
        assert cls["hard"] == {"102"}

    def test_single_color_recognition(self):
        cls = classify_medical_note("不招单色识别不全者")
        assert cls["hard"] == {"103"}

    def test_naked_vision(self):
        cls = classify_medical_note("裸眼视力≥4.8")
        assert "202" in cls["hard"]

    def test_soft_no_hard(self):
        cls = classify_medical_note("请色盲色弱的考生慎重报考")
        assert cls["hard"] == set()
        assert cls["soft"] == {"101", "102"}

    def test_liver_soft(self):
        cls = classify_medical_note("请转氨酶异常的考生慎重报考")
        assert cls["hard"] == set()
        assert cls["soft"] == {"405"}

    def test_empty(self):
        cls = classify_medical_note("")
        assert cls == {"hard": set(), "soft": set()}


class TestMajorMedicalStatus:
    def test_no_user_codes_ok(self):
        assert major_medical_status("不招色盲色弱", None) == "ok"
        assert major_medical_status("不招色盲色弱", []) == "ok"

    def test_hard_match_exclude(self):
        assert major_medical_status("不招色盲色弱", ["101"]) == "exclude"
        assert major_medical_status("不招色盲", ["102"]) == "exclude"

    def test_hard_no_match_keep(self):
        # 用户勾选色盲(102)，但专业只限制单色识别(103) → 保留
        assert major_medical_status("不招单色识别不全者", ["102"]) == "ok"
        # 用户勾选色弱(101)，专业限制色盲(102) → 保留
        assert major_medical_status("不招色盲", ["101"]) == "ok"

    def test_soft_never_exclude(self):
        assert major_medical_status("请色盲色弱的考生慎重报考", ["101"]) == "ok"
        assert major_medical_status("请转氨酶异常的考生慎重报考", ["405"]) == "ok"

    def test_no_note_ok(self):
        assert major_medical_status("", ["101"]) == "ok"