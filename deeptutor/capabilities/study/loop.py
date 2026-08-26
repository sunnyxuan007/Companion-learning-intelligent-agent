"""辅助学习 LoopCapability：在 chat agent 循环中激活错题分析 / 错题本 / 画像工具。"""

from __future__ import annotations

from importlib import resources
from typing import Any

from deeptutor.capabilities.protocol import PromptBlock
from deeptutor.core.context import UnifiedContext

STUDY_TOOL_NAMES = (
    "analyze_study",
    "mistake_notebook",
    "learner_profile",
)


class StudyLoopCapability:
    name = "study"
    owned_tools = STUDY_TOOL_NAMES

    def is_active(self, context: UnifiedContext) -> bool:
        return bool(context.metadata.get("study_mode"))

    def system_block(
        self,
        context: UnifiedContext,
        *,
        language: str,
        prompts: dict[str, Any],
    ) -> PromptBlock | None:
        if not self.is_active(context):
            return None
        content = _load_prompt(language)
        override = _prompt_text(prompts, ("study", "system"))
        if override:
            content = override
        return PromptBlock("study", content)

    async def pre_loop(
        self,
        context: UnifiedContext,
        stream: Any,
        usage: Any = None,
    ) -> PromptBlock | None:
        """把学习者画像摘要注入 system prompt，让 AI 在对话中感知用户学科强弱。"""
        if not self.is_active(context):
            return None
        try:
            from deeptutor.services.custom.learner_profile_service import compute_learner_profile

            profile = compute_learner_profile(context.session_id)
            summary = profile.get("profile_summary", "")
            if not summary:
                return None
            return PromptBlock("learner_profile", f"学习者画像：{summary}")
        except Exception:
            return None

    def augment_kwargs(
        self,
        tool_name: str,
        kwargs: dict[str, Any],
        context: UnifiedContext,
    ) -> dict[str, Any]:
        if self.is_active(context) and tool_name in STUDY_TOOL_NAMES:
            updated = dict(kwargs)
            if "user_id" not in updated:
                updated["user_id"] = context.session_id
            return updated
        return kwargs

    def pre_loop_seed(self, context: UnifiedContext) -> str:
        _ = context
        return ""


def _prompt_text(prompts: dict[str, Any], path: tuple[str, ...]) -> str:
    value: Any = prompts
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return value if isinstance(value, str) and value else ""


def _load_prompt(language: str) -> str:
    lang = "zh" if language.lower().startswith("zh") else "en"
    try:
        prompt = resources.files(__package__).joinpath("prompts", lang, "system.md")
        return prompt.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, TypeError):
        return _default_prompt()


def _default_prompt() -> str:
    return (
        "You are now in 辅助学习 (study assistance) mode. "
        "Your goal is to help the user analyze mistakes/exams/homework and build "
        "their mistake notebook and learner profile.\n\n"
        "Workflow:\n"
        "1. When the user uploads a mistake / exam / homework, use `analyze_study` "
        "to analyze it, give the answer and explanation, and file it into the mistake notebook.\n"
        "2. Use `mistake_notebook` to show the notebook and weak knowledge points.\n"
        "3. Use `learner_profile` to show subject mastery and preferred majors.\n"
        "4. Connect the profile to college admission: stronger subjects → fitting majors."
    )
