from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deeptutor.capabilities.volunteer.loop import VolunteerLoopCapability
from deeptutor.core.context import UnifiedContext


@pytest.fixture
def cap() -> VolunteerLoopCapability:
    return VolunteerLoopCapability()


def test_is_active_true(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"volunteer_mode": True},
    )
    assert cap.is_active(ctx) is True


def test_is_active_false(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={},
    )
    assert cap.is_active(ctx) is False


def test_is_active_explicit_false(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"volunteer_mode": False},
    )
    assert cap.is_active(ctx) is False


def test_system_block_inactive(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(session_id="s1", user_message="test")
    block = cap.system_block(ctx, language="zh", prompts={})
    assert block is None


def test_system_block_active(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="zh",
        metadata={"volunteer_mode": True},
    )
    block = cap.system_block(ctx, language="zh", prompts={})
    assert block is not None
    assert len(block.content) > 0


def test_system_block_english(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="en",
        metadata={"volunteer_mode": True},
    )
    block = cap.system_block(ctx, language="en", prompts={})
    assert block is not None


def test_system_block_fallback_on_missing_file(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="fr",
        metadata={"volunteer_mode": True},
    )
    block = cap.system_block(ctx, language="fr", prompts={})
    assert block is not None


def test_system_block_respects_prompts_override(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="zh",
        metadata={"volunteer_mode": True},
    )
    block = cap.system_block(ctx, language="zh", prompts={"volunteer": {"system": "自定义提示词"}})
    assert block is not None
    assert "自定义提示词" in block.content


def test_augment_kwargs_injects_user_id(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="test-session",
        user_message="test",
        metadata={"volunteer_mode": True},
    )
    kwargs = cap.augment_kwargs("college_search", {"province": "广东"}, ctx)
    assert kwargs.get("user_id") == "test-session"


def test_augment_kwargs_does_not_override(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="test-session",
        user_message="test",
        metadata={"volunteer_mode": True},
    )
    kwargs = cap.augment_kwargs("college_search", {"province": "广东", "user_id": "existing"}, ctx)
    assert kwargs["user_id"] == "existing"


def test_augment_kwargs_ignores_non_owned_tools(cap: VolunteerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"volunteer_mode": True},
    )
    kwargs = cap.augment_kwargs("web_fetch", {"url": "http://example.com"}, ctx)
    assert "user_id" not in kwargs


def test_owned_tools_are_defined(cap: VolunteerLoopCapability) -> None:
    tools = cap.owned_tools
    assert "college_search" in tools
    assert "volunteer_score" in tools
    assert "volunteer_recommend" in tools


def test_pre_loop_seed_empty(cap: VolunteerLoopCapability) -> None:
    ctx = MagicMock()
    assert cap.pre_loop_seed(ctx) == ""


async def test_pre_loop_injects_synthesized_profile(
    cap: VolunteerLoopCapability, monkeypatch
) -> None:
    """pre_loop 走统一合成入口：定量（错题本）+ 定性（L3），与 Web API 口径一致。"""
    import deeptutor.services.custom.learner_profile_service as lps

    captured: dict[str, str] = {}

    def _fake_build(user_id: str, l3_profile=None):
        captured["user_id"] = user_id
        return {
            "_subjects": [{"subject": "数学", "count": 2, "avg_accuracy": 0.8, "source": "study_records"}],
            "_learner_profile": {
                "identity": ["高三理科生"],
                "learning_style": [],
                "knowledge_level": [],
                "goals": [],
                "career_interests": ["计算机"],
                "location_prefs": [],
                "strengths": ["数学"],
                "weaknesses": [],
                "weak_knowledge_points": [],
            },
        }

    monkeypatch.setattr(lps, "build_academic_fit_inputs", _fake_build)

    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"volunteer_mode": True},
    )
    block = await cap.pre_loop(ctx, MagicMock(), usage=None)

    assert captured["user_id"] == "s1"
    assert block is not None
    assert "身份: 高三理科生" in block.content
    assert "职业兴趣: 计算机" in block.content
    assert "学科优势: 数学" in block.content
    # metadata 已注入合成画像（供 augment_kwargs 透传给工具）
    stored = ctx.metadata["_volunteer_learner_profile"]
    assert stored["_subjects"][0]["avg_accuracy"] == 0.8
    assert stored["identity"] == ["高三理科生"]


async def test_pre_loop_failure_is_swallowed(cap: VolunteerLoopCapability, monkeypatch) -> None:
    """合成失败不阻断 chat 循环（返回 None）。"""
    import deeptutor.services.custom.learner_profile_service as lps

    def _boom(user_id: str, l3_profile=None):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(lps, "build_academic_fit_inputs", _boom)

    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"volunteer_mode": True},
    )
    assert await cap.pre_loop(ctx, MagicMock(), usage=None) is None
