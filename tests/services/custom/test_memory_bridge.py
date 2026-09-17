"""L3 原生画像桥接测试：section 解析 / preferences 关键词 / 空文档 / 异常安全。

背景：原生 L3 ``profile`` slot 的 section 是「身份 / 学习风格 / 知识水平」
（见 memory/prompts/zh.yaml 的 slots 定义），旧解析逻辑按「优势/薄弱」匹配
永远取不到内容。本测试锁定对齐后的行为。
"""

from __future__ import annotations

from deeptutor.services.custom.memory_bridge import (
    extract_learner_profile,
    format_learner_briefing,
    read_l3_profile,
)
from deeptutor.services.memory.document import Document, Entry


def _doc(sections: dict[str, list[str]], title: str = "") -> Document:
    return Document(
        title=title,
        sections=[
            (name, [Entry(id=f"m_{i}", section=name, text=text) for i, text in enumerate(texts)])
            for name, texts in sections.items()
        ],
    )


class TestExtractLearnerProfile:
    def test_native_profile_sections_parsed(self):
        """原生 section（身份/学习风格/知识水平）必须被正确归类。"""
        profile_doc = _doc(
            {
                "身份": ["在 3 次 chat 互动中，用户自述为高三理科生"],
                "学习风格": ["在 2 次 notebook 互动中，用户偏好图示讲解"],
                "知识水平": ["在 5 次 solve 互动中，用户对导数掌握较好"],
            }
        )
        result = extract_learner_profile(profile_doc, _doc({}))
        assert result["identity"] == ["在 3 次 chat 互动中，用户自述为高三理科生"]
        assert result["learning_style"] == ["在 2 次 notebook 互动中，用户偏好图示讲解"]
        assert result["knowledge_level"] == ["在 5 次 solve 互动中，用户对导数掌握较好"]
        assert result["other_profile"] == []

    def test_unknown_profile_section_goes_to_other(self):
        profile_doc = _doc({"杂项": ["一些未归类的观察"]})
        result = extract_learner_profile(profile_doc, _doc({}))
        assert result["other_profile"] == ["一些未归类的观察"]
        assert result["identity"] == []

    def test_english_section_names(self):
        profile_doc = _doc(
            {"Identity": ["self-reported STEM student"], "Learning Style": ["prefers examples"]}
        )
        result = extract_learner_profile(profile_doc, _doc({}))
        assert result["identity"] == ["self-reported STEM student"]
        assert result["learning_style"] == ["prefers examples"]

    def test_preferences_career_and_location(self):
        prefs_doc = _doc(
            {
                "Preferences": [
                    "用户想读计算机专业",
                    "用户偏好南方城市",
                    "用户喜欢在早上学习",
                ]
            }
        )
        result = extract_learner_profile(_doc({}), prefs_doc)
        assert result["career_interests"] == ["用户想读计算机专业"]
        assert result["location_prefs"] == ["用户偏好南方城市"]
        assert result["other_preferences"] == ["用户喜欢在早上学习"]

    def test_strengths_weaknesses_empty_by_design(self):
        """定量强弱学科由错题本提供，原生 L3 不产出（兼容键恒为空）。"""
        profile_doc = _doc({"身份": ["学生"]})
        result = extract_learner_profile(profile_doc, _doc({}))
        assert result["strengths"] == []
        assert result["weaknesses"] == []

    def test_empty_docs_return_empty_lists(self):
        result = extract_learner_profile(_doc({}), _doc({}))
        for key in (
            "identity",
            "learning_style",
            "knowledge_level",
            "goals",
            "career_interests",
            "location_prefs",
        ):
            assert result[key] == []

    def test_blank_entry_text_skipped(self):
        profile_doc = _doc({"身份": ["  ", "有效内容"]})
        result = extract_learner_profile(profile_doc, _doc({}))
        assert result["identity"] == ["有效内容"]


class TestReadL3Profile:
    def test_read_l3_profile_returns_dict(self):
        """L3 目录为空时也必须返回 dict（不抛异常）。"""
        result = read_l3_profile()
        assert isinstance(result, dict)

    def test_read_l3_profile_exception_safe(self, monkeypatch):
        import deeptutor.services.custom.memory_bridge as mb

        def _boom():
            raise RuntimeError("store unavailable")

        monkeypatch.setattr(mb, "get_memory_store", _boom)
        assert mb.read_l3_profile() == {}


class TestFormatLearnerBriefing:
    def test_renders_qualitative_and_quantitative(self):
        profile_data = {
            "identity": ["高三理科生"],
            "learning_style": ["偏好图示"],
            "knowledge_level": ["导数掌握较好"],
            "goals": ["冲刺 985"],
            "career_interests": ["计算机"],
            "location_prefs": ["南方"],
            "strengths": ["数学"],
            "weaknesses": ["英语"],
            "weak_knowledge_points": [{"point": "导数", "subject": "数学"}],
        }
        text = format_learner_briefing(profile_data, subjects=[{"subject": "数学", "count": 2, "avg_accuracy": 0.8}])
        assert "身份: 高三理科生" in text
        assert "学习风格: 偏好图示" in text
        assert "知识水平: 导数掌握较好" in text
        assert "学习目标: 冲刺 985" in text
        assert "职业兴趣: 计算机" in text
        assert "地域偏好: 南方" in text
        assert "学科优势: 数学" in text
        assert "薄弱学科: 英语" in text
        assert "待巩固知识点: 导数" in text
        assert "数学: 80%" in text

    def test_empty_profile_returns_empty_string(self):
        assert format_learner_briefing({}, subjects=None) == ""
