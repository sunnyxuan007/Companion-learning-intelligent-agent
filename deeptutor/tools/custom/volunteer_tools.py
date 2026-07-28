from __future__ import annotations

import json
import time
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.services.custom.college_dao import get_college_detail, search_colleges
from deeptutor.services.custom.user_settings_dao import get_user_weights, reset_user_weights, set_user_weights
from deeptutor.services.custom.volunteer_scorer import generate_recommendations, score_college_major


class CollegeSearchTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="college_search",
            description="Search colleges by province, level, type, or keyword. Returns a list of matching colleges with basic info.",
            parameters=[
                ToolParameter(name="province", type="string", description="Province filter", required=False),
                ToolParameter(name="level", type="string", description="Level: 985/211/双一流/普通/专科", required=False),
                ToolParameter(name="college_type", type="string", description="Type: 综合/理工/师范/医药/...", required=False),
                ToolParameter(name="keyword", type="string", description="College name keyword", required=False),
                ToolParameter(name="limit", type="number", description="Max results", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        colleges = search_colleges(
            province=kwargs.get("province"),
            level=kwargs.get("level"),
            college_type=kwargs.get("college_type"),
            keyword=kwargs.get("keyword"),
            limit=int(kwargs.get("limit", 50)),
        )
        if not colleges:
            return ToolResult(content="未找到匹配的院校。")
        lines = [f"找到 {len(colleges)} 所院校:"]
        for c in colleges:
            level_tag = f"[{c['level']}]" if c.get("level") else ""
            lines.append(f"  {c['name']} {level_tag} - {c['province']}{c['city']} ({c.get('type','')})")
        return ToolResult(
            content="\n".join(lines),
            metadata={"count": len(colleges), "colleges": colleges[:10]},
        )


class VolunteerScoreTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volunteer_score",
            description="Calculate the comprehensive matching score for a specific college (and optionally major) against user preferences. Factors: dorm, city vitality, cost, employment rate. Respects user-customized weights.",
            parameters=[
                ToolParameter(name="college_id", type="string", description="College ID"),
                ToolParameter(name="major_id", type="string", description="Optional: major ID", required=False),
                ToolParameter(name="user_rank", type="number", description="User's estimated province rank", required=False),
                ToolParameter(name="province", type="string", description="User's province for province-specific rank data", required=False),
                ToolParameter(name="exam_category", type="string", description="User's exam category (物理/历史)", required=False),
                ToolParameter(name="user_id", type="string", description="User identifier (for custom weights)", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        college_id = str(kwargs.get("college_id", ""))
        major_id = kwargs.get("major_id")
        user_rank = kwargs.get("user_rank")
        user_id = str(kwargs.get("user_id", "default"))

        detail = get_college_detail(college_id)
        if not detail:
            return ToolResult(content=f"未找到院校: {college_id}")

        major_detail = None
        if major_id:
            for m in detail.get("majors", []):
                if m["id"] == major_id:
                    major_detail = m
                    break
            if not major_detail:
                return ToolResult(content=f"未找到该院校下的专业: {major_id}")

        profile = {}
        if user_rank:
            profile["rank"] = int(user_rank)
        if kwargs.get("province"):
            profile["province"] = str(kwargs["province"])
        if kwargs.get("exam_category"):
            profile["exam_category"] = str(kwargs["exam_category"])

        weights = get_user_weights(user_id)
        result = score_college_major(
            detail,
            major=major_detail,
            user_profile=profile,
            weights=weights,
        )

        lines = [
            f"院校: {detail['name']}",
        ]
        if major_detail:
            lines.append(f"专业: {major_detail['name']}")
        lines.append(f"综合匹配分: {result['total_score']:.2f}")
        lines.append("")
        for key, explanation in result["explanations"].items():
            score = result["detail_scores"].get(key, 0)
            lines.append(f"  {key}: {explanation} (权重贡献: {score:.3f})")

        return ToolResult(
            content="\n".join(lines),
            metadata=result,
        )


class VolunteerRecommendTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volunteer_recommend",
            description="Generate a full college application recommendation plan with reach-steady-safe tiers. Based on multi-factor scoring model. Respects user-customized weights.",
            parameters=[
                ToolParameter(name="province", type="string", description="User's province", required=False),
                ToolParameter(name="user_rank", type="number", description="User's estimated province rank"),
                ToolParameter(name="exam_category", type="string", description="User's exam category (物理/历史)", required=False),
                ToolParameter(name="level", type="string", description="Preferred college level (985/211/双一流)", required=False),
                ToolParameter(name="major_keyword", type="string", description="Preferred major keyword", required=False),
                ToolParameter(name="limit", type="number", description="Number of recommendations", required=False),
                ToolParameter(name="user_id", type="string", description="User identifier (for custom weights)", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        colleges = search_colleges(
            province=kwargs.get("province"),
            level=kwargs.get("level"),
            limit=100,
        )
        user_rank = kwargs.get("user_rank")
        user_id = str(kwargs.get("user_id", "default"))
        profile = {}
        if user_rank:
            profile["rank"] = int(user_rank)
        if kwargs.get("province"):
            profile["province"] = str(kwargs["province"])
        if kwargs.get("exam_category"):
            profile["exam_category"] = str(kwargs["exam_category"])

        weights = get_user_weights(user_id)
        result = generate_recommendations(colleges, user_profile=profile, weights=weights, top_n=int(kwargs.get("limit", 10)))

        lines = ["# 志愿推荐方案", ""]
        for tier_name, tier_key in [("冲刺志愿", "reach"), ("稳妥志愿", "steady"), ("保底志愿", "safe")]:
            items = result["tiers"].get(tier_key, [])
            if not items:
                continue
            lines.append(f"## {tier_name} ({len(items)}个)")
            for item in items:
                c = item["college"]
                lines.append(f"  {c['name']} - 匹配分 {item['total_score']:.2f}")
            lines.append("")

        return ToolResult(
            content="\n".join(lines),
            metadata={
                "tiers": {k: [{"college_id": i["college"]["id"], "score": i["total_score"]} for i in v]
                          for k, v in result["tiers"].items()},
            },
        )


class VolunteerWeightsTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="volunteer_weights",
            description="View, set, or reset the multi-factor scoring weights for college recommendation. "
                        "Factors: academic_fit (学业匹配度), admission_prob (录取概率), dorm_quality (宿舍条件), "
                        "city_vitality (城市活力), cost_efficiency (生活成本), employment (就业前景), "
                        "career_alignment (职业契合度). Weights should sum to 1.0.",
            parameters=[
                ToolParameter(name="mode", type="string", description="Operation: 'get' to view current weights, 'set' to update weights, 'reset' to restore defaults"),
                ToolParameter(name="weights_json", type="string", description="JSON string of weights (only for 'set' mode), e.g. '{\"employment\": 0.30, \"admission_prob\": 0.25}'", required=False),
                ToolParameter(name="user_id", type="string", description="User identifier", required=False),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS

        user_id = str(kwargs.get("user_id", "default"))
        mode = str(kwargs.get("mode", "get"))

        if mode == "reset":
            weights = reset_user_weights(user_id)
            return ToolResult(
                content="权重已重置为默认值。",
                metadata={"weights": weights},
            )

        if mode == "set":
            raw = kwargs.get("weights_json")
            if not raw:
                return ToolResult(content="请提供 weights_json 参数。")
            try:
                new_weights = json.loads(raw)
            except json.JSONDecodeError as e:
                return ToolResult(content=f"JSON 格式错误: {e}")

            current = get_user_weights(user_id)
            current.update(new_weights)
            total = sum(current.values())
            if abs(total - 1.0) > 0.01:
                return ToolResult(
                    content=f"权重总和为 {total:.2f}，应为 1.0。请调整后重试。"
                )
            set_user_weights(user_id, current)

            try:
                from deeptutor.services.custom.memory_bridge import write_preference_signal
                await write_preference_signal(
                    text=f"调整志愿评分权重: {json.dumps(new_weights, ensure_ascii=False)}",
                    trace_id=f"volunteer_weights:{user_id}:{int(time.time())}",
                )
            except Exception:
                pass

            return ToolResult(
                content=f"权重已更新。\n{_format_weights(current)}",
                metadata={"weights": current},
            )

        weights = get_user_weights(user_id)
        return ToolResult(
            content=f"当前评分权重:\n{_format_weights(weights)}",
            metadata={"weights": weights},
        )


def _format_weights(weights: dict[str, float]) -> str:
    from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS

    lines = []
    labels = {
        "academic_fit": "学业匹配度", "admission_prob": "录取概率",
        "dorm_quality": "宿舍条件", "city_vitality": "城市活力",
        "cost_efficiency": "生活成本", "employment": "就业前景",
        "career_alignment": "职业契合度",
    }
    for key, default in VOLUNTEER_DEFAULT_WEIGHTS.items():
        current = weights.get(key, default)
        bar = "█" * int(current * 20) + "░" * (20 - int(current * 20))
        label = labels.get(key, key)
        diff = current - default
        arrow = f" (+{diff:.0%})" if diff > 0.005 else f" ({diff:.0%})" if diff < -0.005 else ""
        lines.append(f"  {label}: {current:.0%} {bar}{arrow}")
    lines.append("  ─────────────────────")
    lines.append(f"  总计: {sum(weights.values()):.0%}")
    return "\n".join(lines)
