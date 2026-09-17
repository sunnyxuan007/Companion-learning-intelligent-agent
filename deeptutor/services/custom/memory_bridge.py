"""L3 原生记忆 ↔ 画像桥接。

职责划分（画像分层互补）：
- **定性画像**：由 DeepTutor 原生 L3 记忆（记忆策展员 LLM 归纳）提供，
  slot 为 ``profile``（身份/学习风格/知识水平）与 ``preferences``（偏好）。
  本模块负责**读取并解析**它。
- **定量画像**：由错题本 + 成绩确定性计算（``learner_profile_service``）提供。
- 两者在 ``build_academic_fit_inputs()`` 中**分区合并**，键不重叠 → 互补而非覆盖。

本模块不产生定量画像，也不写回计算画像（避免污染原生记忆）。
"""

from __future__ import annotations

import logging
from typing import Any

from deeptutor.services.memory.document import Document
from deeptutor.services.memory.store import get_memory_store

logger = logging.getLogger(__name__)

# 原生 L3 profile slot 的 section（见 memory/prompts/zh.yaml 的 slots 定义）
# 映射到本模块的定性字段名。
_PROFILE_SECTION_MAP: dict[str, str] = {
    "身份": "identity",
    "identity": "identity",
    "学习风格": "learning_style",
    "learning style": "learning_style",
    "learning_style": "learning_style",
    "style": "learning_style",
    "知识水平": "knowledge_level",
    "knowledge level": "knowledge_level",
    "knowledge_level": "knowledge_level",
    "level": "knowledge_level",
    "目标": "goals",
    "goal": "goals",
    "goals": "goals",
}

# preferences slot 的关键词 → 字段
_CAREER_KEYWORDS = ("职业", "专业", "想读", "想学", "career", "major")
_LOCATION_KEYWORDS = ("地域", "城市", "省份", "地区", "location", "city", "region")


def _classify_profile_section(section_name: str) -> str:
    """把原生 profile section 名映射到定性字段名（未匹配归 other_profile）。"""
    key = section_name.strip().lower()
    if key in _PROFILE_SECTION_MAP:
        return _PROFILE_SECTION_MAP[key]
    # 中文 section 名 lower() 后不变，再试一次去空格匹配
    compact = section_name.strip()
    if compact in _PROFILE_SECTION_MAP:
        return _PROFILE_SECTION_MAP[compact]
    return "other_profile"


def extract_learner_profile(
    profile_doc: Document,
    prefs_doc: Document,
) -> dict[str, Any]:
    """从 L3 ``profile`` + ``preferences`` 文档提取**定性**画像。

    返回结构（定性字段，全部为 list[str]）：
    - ``identity`` / ``learning_style`` / ``knowledge_level`` — 原生 profile slot
    - ``goals`` — 目标类 section（若存在）
    - ``career_interests`` / ``location_prefs`` / ``other_preferences`` — preferences slot
    - ``other_profile`` — profile 中未归类 section

    兼容字段 ``strengths`` / ``weaknesses`` 恒为空列表：定量强弱学科由错题本提供，
    原生 L3 不承担该职责（此处保留键仅为向后兼容旧调用方）。
    """
    qualitative: dict[str, list[str]] = {
        "identity": [],
        "learning_style": [],
        "knowledge_level": [],
        "goals": [],
        "other_profile": [],
        "career_interests": [],
        "location_prefs": [],
        "other_preferences": [],
    }

    # ── profile slot：按原生 section 归类 ──
    for section_name, entries in profile_doc.sections:
        bucket = _classify_profile_section(section_name)
        for entry in entries:
            text = entry.text.strip()
            if text:
                qualitative[bucket].append(text)

    # ── preferences slot：关键词识别职业/地域 ──
    for section_name, entries in prefs_doc.sections:
        section_lower = section_name.lower()
        for entry in entries:
            text = entry.text.strip()
            if not text:
                continue
            haystack = f"{section_lower} {text.lower()}"
            if any(kw in haystack for kw in _CAREER_KEYWORDS):
                qualitative["career_interests"].append(text)
            elif any(kw in haystack for kw in _LOCATION_KEYWORDS):
                qualitative["location_prefs"].append(text)
            else:
                qualitative["other_preferences"].append(text)

    result: dict[str, Any] = dict(qualitative)
    # 兼容字段：定量画像由错题本提供，此处不产出
    result["strengths"] = []
    result["weaknesses"] = []
    return result


def read_l3_profile() -> dict[str, Any]:
    """读取 L3 原生画像（定性）—— 本模块是读 L3 的唯一入口。

    L3 目录为空 / 文件不存在 / 解析异常时返回空 dict（异常安全，不阻断主流程）。
    """
    try:
        store = get_memory_store()
        return extract_learner_profile(
            store.read_doc("L3", "profile"),
            store.read_doc("L3", "preferences"),
        )
    except Exception:
        logger.warning("read_l3_profile failed", exc_info=True)
        return {}


def format_learner_briefing(
    profile_data: dict[str, Any],
    subjects: list[dict[str, Any]] | None = None,
) -> str:
    """把定性 + 定量画像渲染成给 LLM 的简报文本（system prompt 用）。"""
    parts: list[str] = []

    # ── 定性（L3 原生）──
    if profile_data.get("identity"):
        parts.append("身份: " + "; ".join(profile_data["identity"]))
    if profile_data.get("learning_style"):
        parts.append("学习风格: " + "; ".join(profile_data["learning_style"]))
    if profile_data.get("knowledge_level"):
        parts.append("知识水平: " + "; ".join(profile_data["knowledge_level"]))
    if profile_data.get("goals"):
        parts.append("学习目标: " + "; ".join(profile_data["goals"]))
    if profile_data.get("career_interests"):
        parts.append("职业兴趣: " + "; ".join(profile_data["career_interests"]))
    if profile_data.get("location_prefs"):
        parts.append("地域偏好: " + "; ".join(profile_data["location_prefs"]))

    # ── 定量（错题本）──
    if profile_data.get("strengths"):
        parts.append("学科优势: " + "; ".join(profile_data["strengths"]))
    if profile_data.get("weaknesses"):
        parts.append("薄弱学科: " + "; ".join(profile_data["weaknesses"]))
    if profile_data.get("weak_knowledge_points"):
        points = [
            str(w.get("point", ""))
            for w in profile_data["weak_knowledge_points"][:5]
            if w.get("point")
        ]
        if points:
            parts.append("待巩固知识点: " + "; ".join(points))

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
    """写回 L3 preferences（仅限**真实用户偏好信号**）。

    注意：确定性计算的画像（错题本掌握度等）**不应**经此写入，
    否则会污染原生记忆。用户原话偏好、显式权重调整属合法信号。
    """
    try:
        store = get_memory_store()
        await store.write_preference(
            op="add",
            text=text,
            trace_id=trace_id,
        )
    except Exception:
        logger.warning("write_preference_signal failed: %s", text[:80], exc_info=True)
