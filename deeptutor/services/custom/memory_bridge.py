from __future__ import annotations

import logging
from typing import Any

from deeptutor.services.memory.document import Document, Entry
from deeptutor.services.memory.store import get_memory_store

logger = logging.getLogger(__name__)


def extract_learner_profile(
    profile_doc: Document,
    prefs_doc: Document,
) -> dict[str, Any]:
    strengths: list[str] = []
    weaknesses: list[str] = []
    goals: list[str] = []

    for section_name, entries in profile_doc.sections:
        section_lower = section_name.lower()
        for entry in entries:
            text = entry.text.strip()
            if not text:
                continue
            if "strong" in section_lower or "优势" in section_lower:
                strengths.append(text)
            elif "weak" in section_lower or "薄弱" in section_lower:
                weaknesses.append(text)
            elif "goal" in section_lower or "目标" in section_lower:
                goals.append(text)
            else:
                if text.startswith("Strong") or "优势" in text:
                    strengths.append(text)
                elif text.startswith("Weak") or "薄弱" in text:
                    weaknesses.append(text)

    career_interests: list[str] = []
    location_prefs: list[str] = []
    other_prefs: list[str] = []

    for section_name, entries in prefs_doc.sections:
        section_lower = section_name.lower()
        for entry in entries:
            text = entry.text.strip()
            if not text:
                continue
            if "career" in section_lower or "职业" in section_lower:
                career_interests.append(text)
            elif "location" in section_lower or "地域" in section_lower or "城市" in section_lower:
                location_prefs.append(text)
            else:
                other_prefs.append(text)

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "goals": goals,
        "career_interests": career_interests,
        "location_prefs": location_prefs,
        "other_preferences": other_prefs,
    }


def format_learner_briefing(
    profile_data: dict[str, Any],
    subjects: list[dict[str, Any]] | None = None,
) -> str:
    parts: list[str] = []
    if profile_data.get("strengths"):
        parts.append("学科优势: " + "; ".join(profile_data["strengths"]))
    if profile_data.get("weaknesses"):
        parts.append("薄弱学科: " + "; ".join(profile_data["weaknesses"]))
    if profile_data.get("goals"):
        parts.append("学习目标: " + "; ".join(profile_data["goals"]))
    if profile_data.get("career_interests"):
        parts.append("职业兴趣: " + "; ".join(profile_data["career_interests"]))
    if profile_data.get("location_prefs"):
        parts.append("地域偏好: " + "; ".join(profile_data["location_prefs"]))

    if subjects:
        acc_lines: list[str] = []
        for s in subjects:
            name = s.get("subject", "")
            cnt = s.get("count", 0)
            acc = s.get("avg_accuracy")
            if name and acc is not None:
                acc_lines.append(f"{name}: {float(acc)*100:.0f}% ({cnt}次)")
        if acc_lines:
            parts.append("学科正确率: " + " | ".join(acc_lines))

    return "\n".join(parts) if parts else ""


async def write_preference_signal(text: str, trace_id: str) -> None:
    try:
        store = get_memory_store()
        await store.write_preference(
            op="add",
            text=text,
            trace_id=trace_id,
        )
    except Exception:
        logger.warning("write_preference_signal failed: %s", text[:80], exc_info=True)
