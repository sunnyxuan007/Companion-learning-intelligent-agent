"""错题本数据层测试：CRUD / 复习 / 掌握度 / 统计。"""

from __future__ import annotations

import pytest

from deeptutor.services.custom.mistake_dao import (
    add_review,
    create_mistake,
    delete_mistake,
    get_mistake,
    get_mistake_stats,
    list_mistakes,
    update_mistake,
)


@pytest.mark.usefixtures("custom_db")
class TestMistakeDao:
    def test_create_and_get(self):
        m = create_mistake(
            "u1",
            source_type="mistake",
            subject="数学",
            question="求 f(x)=x² 的导数",
            ai_answer="2x",
            ai_explanation="幂函数求导",
            knowledge_points=["导数", "幂函数"],
            difficulty="easy",
        )
        assert m["id"]
        got = get_mistake(m["id"])
        assert got["question"] == "求 f(x)=x² 的导数"
        assert got["knowledge_points"] == ["导数", "幂函数"]
        assert got["mastery"] == 0.3
        assert got["status"] == "open"

    def test_create_with_invalid_fields_falls_back(self):
        m = create_mistake("u1", source_type="unknown", status="weird", subject="物理")
        assert m["source_type"] == "mistake"
        assert m["status"] == "open"

    def test_list_filters(self):
        create_mistake("u1", subject="数学", source_type="mistake", question="q1")
        create_mistake("u1", subject="物理", source_type="paper", question="q2")
        create_mistake("u2", subject="数学", source_type="mistake", question="q3")

        all_u1 = list_mistakes("u1")
        assert len(all_u1) == 2
        math_only = list_mistakes("u1", subject="数学")
        assert len(math_only) == 1 and math_only[0]["question"] == "q1"
        paper_only = list_mistakes("u1", source_type="paper")
        assert len(paper_only) == 1 and paper_only[0]["question"] == "q2"

    def test_update_fields(self):
        m = create_mistake("u1", subject="数学", question="old")
        updated = update_mistake(m["id"], question="new", knowledge_points=["函数"], mastery=0.9)
        assert updated["question"] == "new"
        assert updated["knowledge_points"] == ["函数"]
        assert updated["mastery"] == 0.9

    def test_delete(self):
        m = create_mistake("u1", subject="数学", question="del")
        assert delete_mistake(m["id"]) is True
        assert get_mistake(m["id"]) is None
        assert delete_mistake(m["id"]) is False

    def test_review_updates_mastery_and_status(self):
        m = create_mistake("u1", subject="数学", question="r")
        # 连续三次做对 → mastery 上升且状态变 mastered
        for _ in range(3):
            m = add_review(m["id"], "u1", True)
        assert m["review_count"] == 3
        assert m["mastery"] > 0.8
        assert m["status"] == "mastered"
        # 做错回落
        m = add_review(m["id"], "u1", False)
        assert m["mastery"] < 0.8
        assert m["status"] != "archived"

    def test_review_unknown_mistake_returns_none(self):
        assert add_review("nope", "u1", True) is None

    def test_stats(self):
        create_mistake("u1", subject="数学", knowledge_points=["导数"], mastery=0.3)
        create_mistake("u1", subject="数学", knowledge_points=["导数"], mastery=0.5)
        create_mistake("u1", subject="英语", knowledge_points=["阅读"], mastery=0.9)
        stats = get_mistake_stats("u1")
        assert stats["total"] == 3
        by_subj = {s["subject"]: s for s in stats["by_subject"]}
        assert by_subj["数学"]["count"] == 2
        weak = {w["point"]: w for w in stats["weak_knowledge_points"]}
        assert "导数" in weak
        assert "阅读" not in weak  # mastery 0.9 ≥ 0.6
