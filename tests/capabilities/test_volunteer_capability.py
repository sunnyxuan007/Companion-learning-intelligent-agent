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
