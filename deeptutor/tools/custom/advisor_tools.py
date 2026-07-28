from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.services.custom.advisor_dao import get_advisor_stats, search_advisors


class AdvisorSearchTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="advisor_search",
            description="Search advisor/mentor evaluations by school, college, or name. Returns ratings and review summaries.",
            parameters=[
                ToolParameter(name="school", type="string", description="School name filter", required=False),
                ToolParameter(name="college", type="string", description="College/department name filter", required=False),
                ToolParameter(name="name", type="string", description="Advisor name filter", required=False),
                ToolParameter(name="limit", type="number", description="Max results", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        school = kwargs.get("school")
        college = kwargs.get("college")
        name = kwargs.get("name")
        limit = int(kwargs.get("limit", 20))

        results = search_advisors(
            school=str(school) if school else None,
            college_name=str(college) if college else None,
            name=str(name) if name else None,
            limit=limit,
        )

        if not results:
            return ToolResult(content="未找到匹配的导师评价。")

        stats = get_advisor_stats(
            school=str(school) if school else None,
            name=str(name) if name else None,
        )

        lines = [f"找到 {len(results)} 条导师评价"]
        if stats["count"] > len(results):
            lines.append(f"（共 {stats['count']} 条匹配，平均评分 {stats['avg_score']:.2f}）")
        lines.append("")

        for r in results[:10]:
            review_preview = (r.get("review_text") or "")[:120].replace("\n", " ")
            lines.append(
                f"  [{r['school']}] {r['name']} {r.get('college','') or ''} "
                f"评分: {r['score']}"
            )
            if review_preview:
                lines.append(f"    {review_preview}...")

        if len(results) > 10:
            lines.append(f"  ... 还有 {len(results) - 10} 条")

        return ToolResult(
            content="\n".join(lines),
            metadata={
                "count": len(results),
                "total_matches": stats.get("count", 0),
                "avg_score": stats.get("avg_score"),
            },
        )
