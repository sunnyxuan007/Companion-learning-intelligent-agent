from __future__ import annotations

import logging
from importlib import resources
from typing import Any

from deeptutor.capabilities.protocol import PromptBlock
from deeptutor.core.context import UnifiedContext

logger = logging.getLogger(__name__)

VOLUNTEER_TOOL_NAMES = (
    "college_search",
    "volunteer_score",
    "volunteer_recommend",
    "volunteer_weights",
)

_MEMORY_PROFILE_KEY = "_volunteer_learner_profile"


class VolunteerLoopCapability:
    name = "volunteer"
    owned_tools = VOLUNTEER_TOOL_NAMES

    def is_active(self, context: UnifiedContext) -> bool:
        return bool(context.metadata.get("volunteer_mode"))

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
        override = _prompt_text(prompts, ("volunteer", "system"))
        if override:
            content = override
        return PromptBlock("volunteer", content)

    async def pre_loop(
        self,
        context: UnifiedContext,
        stream: Any,
        usage: Any = None,
    ) -> PromptBlock | None:
        if not self.is_active(context):
            return None
        try:
            from deeptutor.services.custom.memory_bridge import (
                extract_learner_profile,
                format_learner_briefing,
            )
            from deeptutor.services.custom.study_dao import get_subject_summary
            from deeptutor.services.memory.store import get_memory_store

            store = get_memory_store()
            profile_data = extract_learner_profile(
                store.read_doc("L3", "profile"),
                store.read_doc("L3", "preferences"),
            )

            subjects = get_subject_summary(context.session_id)
            if subjects:
                profile_data["_subjects"] = subjects

            context.metadata[_MEMORY_PROFILE_KEY] = profile_data

            briefing = format_learner_briefing(profile_data, subjects)
            return PromptBlock("learner_profile", briefing) if briefing else None
        except Exception:
            logger.warning("volunteer pre_loop failed", exc_info=True)
            return None

    def augment_kwargs(
        self,
        tool_name: str,
        kwargs: dict[str, Any],
        context: UnifiedContext,
    ) -> dict[str, Any]:
        if self.is_active(context) and tool_name in VOLUNTEER_TOOL_NAMES:
            updated = dict(kwargs)
            if "user_id" not in updated:
                updated["user_id"] = context.session_id
            p = context.metadata.get(_MEMORY_PROFILE_KEY)
            if p:
                if p.get("_subjects"):
                    updated["_subjects"] = p["_subjects"]
                clean = {k: v for k, v in p.items() if not k.startswith("_")}
                updated["_learner_profile"] = clean
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
        "You are now in 志愿填报 (college application) mode. "
        "Your goal is to help the user build a college application plan.\n\n"
        "Workflow:\n"
        "1. Collect the user's 省份 (province), 分数/位次 (score/rank), and preferences.\n"
        "2. Use `college_search` to find matching colleges.\n"
        "3. Use `volunteer_score` to evaluate individual college-major matches.\n"
        "4. Use `volunteer_recommend` to generate a full plan with reach-steady-safe tiers.\n"
        "5. Explain each recommendation by referencing the multi-factor scores "
        "(dorm quality, city vitality, cost, employment rate, etc.).\n\n"
        "Always provide reasons for each recommendation."
    )
