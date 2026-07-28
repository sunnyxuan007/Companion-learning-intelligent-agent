from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deeptutor.capabilities.career.loop import CareerLoopCapability
from deeptutor.core.context import UnifiedContext


@pytest.fixture
def cap() -> CareerLoopCapability:
    return CareerLoopCapability()


def test_is_active_true(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"career_mode": True},
    )
    assert cap.is_active(ctx) is True


def test_is_active_false(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={},
    )
    assert cap.is_active(ctx) is False


def test_system_block_inactive(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(session_id="s1", user_message="test")
    block = cap.system_block(ctx, language="zh", prompts={})
    assert block is None


def test_system_block_active(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="zh",
        metadata={"career_mode": True},
    )
    block = cap.system_block(ctx, language="zh", prompts={})
    assert block is not None
    assert len(block.content) > 0


def test_system_block_english(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="en",
        metadata={"career_mode": True},
    )
    block = cap.system_block(ctx, language="en", prompts={})
    assert block is not None


def test_system_block_respects_prompts_override(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        language="zh",
        metadata={"career_mode": True},
    )
    block = cap.system_block(ctx, language="zh", prompts={"career": {"system": "自定义生涯提示词"}})
    assert block is not None
    assert "自定义生涯提示词" in block.content


def test_augment_kwargs_injects_user_id(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="test-session",
        user_message="test",
        metadata={"career_mode": True},
    )
    kwargs = cap.augment_kwargs("gap_analysis", {"subject": "数学"}, ctx)
    assert kwargs.get("user_id") == "test-session"


def test_augment_kwargs_does_not_override(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="test-session",
        user_message="test",
        metadata={"career_mode": True},
    )
    kwargs = cap.augment_kwargs("gap_analysis", {"user_id": "existing"}, ctx)
    assert kwargs["user_id"] == "existing"


def test_augment_kwargs_ignores_non_owned_tools(cap: CareerLoopCapability) -> None:
    ctx = UnifiedContext(
        session_id="s1",
        user_message="test",
        metadata={"career_mode": True},
    )
    kwargs = cap.augment_kwargs("web_fetch", {"url": "http://example.com"}, ctx)
    assert "user_id" not in kwargs


def test_owned_tools_are_defined(cap: CareerLoopCapability) -> None:
    tools = cap.owned_tools
    assert "gap_analysis" in tools
    assert "study_dashboard" in tools
    assert "college_search" in tools


def test_pre_loop_seed_empty(cap: CareerLoopCapability) -> None:
    ctx = MagicMock()
    assert cap.pre_loop_seed(ctx) == ""
