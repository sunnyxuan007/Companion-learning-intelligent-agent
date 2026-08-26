"""辅助学习工具：AI 分析错题 / 查询错题本 / 查看学习者画像。

这些工具注册进 `CUSTOM_TOOL_TYPES` 后，聊天 agent（chat / career / volunteer /
study 模式）都能通过 function calling 调用，从而在对话中直接：
- 分析用户上传的错题并把结果整理进错题本
- 查询错题本与薄弱知识点
- 查看画像及画像推导的「适合专业」倾向
"""

from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult


class AnalyzeStudyTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_study",
            description=(
                "Analyze a mistake/exam/homework item uploaded by the user: "
                "produce the answer, explanation, knowledge points, and mistake reason, "
                "then file it into the mistake notebook and refresh the learner profile. "
                "Call this when the user pastes a wrong question, exam paper, or homework."
            ),
            parameters=[
                ToolParameter(name="user_id", type="string", description="User identifier"),
                ToolParameter(name="subject", type="string", description="Subject, e.g. 数学/物理/英语"),
                ToolParameter(name="content", type="string", description="The question / paper / homework text"),
                ToolParameter(name="source_type", type="string", description="mistake|paper|homework", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "default"))
        subject = str(kwargs.get("subject", ""))
        content = str(kwargs.get("content", "") or "")
        source_type = str(kwargs.get("source_type", "mistake"))
        if not content.strip():
            return ToolResult(content="内容为空，请提供需要分析的题目或作业文本。")

        from deeptutor.services.custom.ai_tutor_service import get_ai_tutor_service

        result = await get_ai_tutor_service().analyze_content(
            user_id, subject=subject, source_type=source_type, content=content
        )

        lines = [
            f"已分析并存入错题本（#{result['mistake_id']}）",
            f"科目: {result['subject'] or '未知'}",
            f"题目: {(result['question'] or '')[:120]}",
            f"答案: {(result['answer'] or '')[:200]}",
            f"解析: {(result['explanation'] or '')[:200]}",
            f"知识点: {', '.join(result['knowledge_points']) or '无'}",
            f"错因: {result['mistake_reason'] or '无'}",
            f"难度: {result['difficulty']}",
        ]
        if result.get("suggestions"):
            lines.append(f"学习建议: {result['suggestions']}")
        if result.get("analysis_status") != "ok":
            lines.append("（AI 分析暂不可用，已保存原文，可稍后补充答案）")
        return ToolResult(content="\n".join(lines), metadata=result)


class MistakeNotebookTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mistake_notebook",
            description=(
                "Query the user's mistake notebook: list mistakes (optionally by subject/status) "
                "or get stats including weak knowledge points. Call this when the user asks "
                "about their mistake book, review list, or weak points."
            ),
            parameters=[
                ToolParameter(name="user_id", type="string", description="User identifier"),
                ToolParameter(name="subject", type="string", description="Filter by subject", required=False),
                ToolParameter(name="stats", type="string", description="Set 'true' to return stats instead of list", required=False),
                ToolParameter(name="limit", type="number", description="Max items", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "default"))
        subject = kwargs.get("subject")
        subject = str(subject) if subject else None
        want_stats = str(kwargs.get("stats", "")).lower() in ("1", "true", "yes")
        limit = int(kwargs.get("limit", 20))

        from deeptutor.services.custom.mistake_dao import get_mistake_stats, list_mistakes

        if want_stats:
            stats = get_mistake_stats(user_id)
            lines = [
                f"错题本共 {stats['total']} 条",
                "按科目: " + " | ".join(f"{s['subject']}({s['count']})" for s in stats["by_subject"]) or "无",
                "按状态: " + (", ".join(f"{k}:{v}" for k, v in stats["by_status"].items()) or "无"),
            ]
            weak = stats["weak_knowledge_points"][:10]
            if weak:
                lines.append("薄弱知识点: " + "、".join(f"{w['point']}({w['fail_count']}次)" for w in weak))
            else:
                lines.append("暂无薄弱知识点，继续保持！")
            return ToolResult(content="\n".join(lines), metadata=stats)

        items = list_mistakes(user_id, subject=subject, limit=min(limit, 50))
        if not items:
            return ToolResult(content="错题本为空，快去上传一道错题吧。", metadata={"count": 0})
        lines = [f"错题本共 {len(items)} 条（最新在前）："]
        for m in items:
            mastery = float(m.get("mastery", 0.3))
            bar = "█" * int(mastery * 10) + "░" * (10 - int(mastery * 10))
            lines.append(
                f"- [{m['status']}] {m.get('subject','?')} {m.get('question','')[:40]} "
                f"掌握度{mastery*100:.0f}% {bar} 复习{m.get('review_count',0)}次"
            )
        return ToolResult(content="\n".join(lines), metadata={"count": len(items)})


class LearnerProfileTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="learner_profile",
            description=(
                "View the learner profile derived from study records and mistake notebook: "
                "per-subject mastery, weak/strong knowledge points, and preferred majors "
                "(fit computed from subject mastery × subject-major weights). "
                "Use this when the user asks about their learning profile, strengths/weaknesses, "
                "or which majors fit them."
            ),
            parameters=[
                ToolParameter(name="user_id", type="string", description="User identifier"),
                ToolParameter(name="majors_top", type="number", description="How many preferred majors to show", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "default"))
        majors_top = int(kwargs.get("majors_top", 5))

        from deeptutor.services.custom.learner_profile_service import (
            compute_learner_profile,
            recommend_majors_by_profile,
        )

        profile = compute_learner_profile(user_id)
        majors = recommend_majors_by_profile(user_id, top_n=majors_top)

        lines = ["学习者画像："]
        mastery = profile.get("subject_mastery", {})
        if mastery:
            acc_lines = [f"{k}: {v['accuracy']*100:.0f}%" for k, v in sorted(mastery.items(), key=lambda x: -x[1]['accuracy'])]
            lines.append("学科掌握度: " + " | ".join(acc_lines))
        weak = profile.get("weak_knowledge_points", [])[:5]
        if weak:
            lines.append("待巩固: " + "、".join(w["point"] for w in weak))
        if majors:
            lines.append("适合专业倾向: " + "、".join(f"{m['major_name']}({m['fit_score']*100:.0f}%)" for m in majors))
        lines.append(f"画像置信度: {profile.get('confidence', 0)*100:.0f}%")
        return ToolResult(
            content="\n".join(lines),
            metadata={
                "subject_mastery": mastery,
                "weak_knowledge_points": profile.get("weak_knowledge_points", []),
                "preferred_majors": majors,
                "confidence": profile.get("confidence", 0),
            },
        )
