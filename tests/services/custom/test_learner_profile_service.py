"""学习者画像引擎测试：学科掌握度 / 薄弱点 / 专业倾向 / 升学注入结构。"""

from __future__ import annotations

import pytest

from deeptutor.services.custom.learner_profile_service import (
    build_academic_fit_inputs,
    compute_learner_profile,
    load_profile,
    recommend_majors_by_profile,
    save_profile,
)
from deeptutor.services.custom.mistake_dao import create_mistake


@pytest.mark.usefixtures("custom_db")
class TestLearnerProfile:
    def test_subject_mastery_from_study_records(self):
        # conftest: user1 数学 85/100、78/100；英语 92/100
        profile = compute_learner_profile("user1")
        mastery = profile["subject_mastery"]
        assert "数学" in mastery and "英语" in mastery
        assert 0.8 <= mastery["数学"]["accuracy"] <= 0.9
        assert mastery["英语"]["accuracy"] >= 0.9

    def test_mistake_penalty_reduces_mastery(self):
        create_mistake("user1", subject="数学", knowledge_points=["导数"], mastery=0.3)
        create_mistake("user1", subject="数学", knowledge_points=["积分"], mastery=0.3)
        profile = compute_learner_profile("user1")
        math_acc = profile["subject_mastery"]["数学"]["accuracy"]
        # 两条未掌握错题 → 惩罚 0.24，应低于纯成绩口径（~0.815）
        assert math_acc <= 0.70
        assert profile["stats"]["open_mistakes"] == 2

    def test_weak_knowledge_points_aggregated(self):
        create_mistake("user1", subject="数学", knowledge_points=["导数", "函数单调性"], mastery=0.3)
        create_mistake("user1", subject="数学", knowledge_points=["导数"], mastery=0.4)
        profile = compute_learner_profile("user1")
        weak = {w["point"]: w for w in profile["weak_knowledge_points"]}
        assert weak["导数"]["fail_count"] == 2
        assert "函数单调性" in weak

    def test_preferred_majors_scored(self):
        # 用户1：英语强、数学中上 → 英语权重高的专业应排前
        profile = compute_learner_profile("user1")
        majors = profile["preferred_majors"]
        assert majors, "应至少有一个专业倾向"
        # BS007 英语权重 0.6
        bs007 = next((m for m in majors if m["major_id"] == "BS007"), None)
        assert bs007 is not None
        assert 0 < bs007["fit_score"] <= 1.0
        # 排序正确性：fit_score 降序
        scores = [m["fit_score"] for m in majors]
        assert scores == sorted(scores, reverse=True)

    def test_recommend_majors_by_profile(self):
        majors = recommend_majors_by_profile("user1", top_n=3)
        assert len(majors) <= 3

    def test_build_academic_fit_inputs_shape(self):
        """升学注入结构必须与 _calc_academic_fit 消费的字段一致。"""
        inputs = build_academic_fit_inputs("user1")
        assert set(inputs.keys()) == {"_subjects", "_learner_profile"}
        subjects = inputs["_subjects"]
        assert all({"subject", "count", "avg_accuracy"} <= set(s) for s in subjects)
        lp = inputs["_learner_profile"]
        assert "strengths" in lp and "weaknesses" in lp
        assert isinstance(lp["strengths"], list) and isinstance(lp["weaknesses"], list)

    def test_save_and_load_profile(self):
        saved = save_profile("user1")
        loaded = load_profile("user1")
        assert loaded is not None
        assert loaded["user_id"] == "user1"
        assert loaded["subject_mastery"] == saved["subject_mastery"]

    def test_empty_user_returns_neutral(self):
        profile = compute_learner_profile("ghost_user")
        assert profile["subject_mastery"] == {}
        assert profile["confidence"] == 0.0
        inputs = build_academic_fit_inputs("ghost_user")
        assert inputs["_subjects"] == []
        assert inputs["_learner_profile"]["strengths"] == []
