from __future__ import annotations

import json
import time
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.services.custom.study_dao import get_gap_analysis, get_study_timeline, upload_study_record
from deeptutor.services.custom.models import StudyRecord


class UploadExamTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="upload_exam",
            description="Upload and parse an exam/quiz result. The LLM should extract weak/strong knowledge points from the user's description before calling this tool.",
            parameters=[
                ToolParameter(name="user_id", type="string", description="User identifier (session user)"),
                ToolParameter(name="subject", type="string", description="Subject name, e.g. '数学', '英语'"),
                ToolParameter(name="score", type="number", description="Score obtained", required=False),
                ToolParameter(name="total", type="number", description="Total possible score", required=False),
                ToolParameter(name="weak_points", type="string", description="Comma-separated weak knowledge points", required=False),
                ToolParameter(name="strong_points", type="string", description="Comma-separated strong knowledge points", required=False),
                ToolParameter(name="record_type", type="string", description="Type: exam, quiz, or homework", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "default"))
        subject = str(kwargs.get("subject", ""))
        score = kwargs.get("score")
        total = kwargs.get("total")
        weak_raw = str(kwargs.get("weak_points", "") or "")
        strong_raw = str(kwargs.get("strong_points", "") or "")
        record_type = str(kwargs.get("record_type", "exam"))

        weak = [w.strip() for w in weak_raw.split(",") if w.strip()]
        strong = [s.strip() for s in strong_raw.split(",") if s.strip()]

        record = StudyRecord(
            id="",
            user_id=user_id,
            record_type=record_type,
            subject=subject,
            title=f"{subject} - {record_type}",
            score=float(score) if score is not None else None,
            total=float(total) if total is not None else None,
            weak_points=weak,
            strong_points=strong,
            created_at=time.time(),
        )
        upload_study_record(record)

        accuracy = ""
        if score is not None and total and float(total) > 0:
            accuracy = f"正确率: {float(score)/float(total)*100:.1f}%"

        return ToolResult(
            content=(
                f"已记录{subject}的{record_type}成绩。{accuracy}\n"
                f"薄弱知识点: {', '.join(weak) if weak else '无'}\n"
                f"优势知识点: {', '.join(strong) if strong else '无'}"
            ),
            metadata={
                "subject": subject,
                "score": score,
                "total": total,
                "weak_points": weak,
                "strong_points": strong,
            },
        )


class StudyDashboardTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="study_dashboard",
            description="View study progress overview for a user, including recent records and per-subject accuracy trends.",
            parameters=[
                ToolParameter(name="user_id", type="string", description="User identifier"),
                ToolParameter(name="days", type="number", description="Number of days to look back", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "default"))
        days = int(kwargs.get("days", 30))
        records = get_study_timeline(user_id, days=days)
        from deeptutor.services.custom.study_dao import get_subject_summary
        subjects = get_subject_summary(user_id)

        lines = [f"近{days}天学习记录共 {len(records)} 条"]
        for s in subjects:
            acc = s["avg_accuracy"] or 0
            bar = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
            lines.append(f"  {s['subject']}: {s['count']}次, 平均正确率 {acc*100:.1f}% {bar}")

        return ToolResult(
            content="\n".join(lines),
            metadata={"record_count": len(records), "subjects": subjects},
        )


class GapAnalysisTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="gap_analysis",
            description="Analyze weak knowledge areas based on past exam/study records and provide targeted improvement suggestions.",
            parameters=[
                ToolParameter(name="user_id", type="string", description="User identifier"),
                ToolParameter(name="subject", type="string", description="Optional: filter by subject", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = str(kwargs.get("user_id", "default"))
        subject = kwargs.get("subject")
        if subject:
            subject = str(subject)

        gap = get_gap_analysis(user_id, subject=subject)

        lines = [
            f"共分析 {gap['total_records']} 条学习记录",
            "",
            "薄弱知识点排名:",
        ]
        for wp in gap["weak_points_ranked"][:10]:
            bar = "█" * wp["count"] + "░" * (10 - wp["count"])
            lines.append(f"  {wp['point']}: 出现{wp['count']}次 {bar}")

        lines.append("")
        lines.append(f"建议: {gap['suggestion']}")

        return ToolResult(
            content="\n".join(lines),
            metadata=gap,
        )
