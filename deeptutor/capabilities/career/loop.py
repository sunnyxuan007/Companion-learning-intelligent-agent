from __future__ import annotations

from importlib import resources
from typing import Any

from deeptutor.capabilities.protocol import PromptBlock
from deeptutor.core.context import UnifiedContext

CAREER_TOOL_NAMES = (
    "gap_analysis",
    "study_dashboard",
    "college_search",
)


class CareerLoopCapability:
    name = "career"
    owned_tools = CAREER_TOOL_NAMES

    def is_active(self, context: UnifiedContext) -> bool:
        return bool(context.metadata.get("career_mode"))

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
        override = _prompt_text(prompts, ("career", "system"))
        if override:
            content = override
        return PromptBlock("career", content)

    def augment_kwargs(
        self,
        tool_name: str,
        kwargs: dict[str, Any],
        context: UnifiedContext,
    ) -> dict[str, Any]:
        if self.is_active(context) and tool_name in CAREER_TOOL_NAMES:
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
        "You are now in 生涯规划 (career planning) mode. "
        "Your goal is to help the user understand their learning profile and "
        "connect it to career and major choices.\n\n"
        "Workflow:\n"
        "1. Use `study_dashboard` to view the user's learning progress.\n"
        "2. Use `gap_analysis` to identify weak areas and learning patterns.\n"
        "3. Analyze the user's strengths and interests to suggest suitable "
        "career paths and college majors.\n"
        "4. Use `college_search` to find colleges strong in the recommended fields.\n\n"
        "Always connect learning data to career recommendations."
    )
