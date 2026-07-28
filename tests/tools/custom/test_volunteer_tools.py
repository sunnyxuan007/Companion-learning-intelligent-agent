from __future__ import annotations

import pytest

from deeptutor.tools.custom.volunteer_tools import (
    CollegeSearchTool,
    VolunteerRecommendTool,
    VolunteerScoreTool,
)


@pytest.mark.asyncio
async def test_college_search_definition() -> None:
    tool = CollegeSearchTool()
    defn = tool.get_definition()
    assert defn.name == "college_search"
    assert any(p.name == "province" for p in defn.parameters)


@pytest.mark.asyncio
async def test_college_search_empty(mock_dao: dict) -> None:
    mock_dao["search"].return_value = []
    tool = CollegeSearchTool()
    result = await tool.execute(keyword="不存在的大学")
    assert result.success
    assert "未找到" in result.content


@pytest.mark.asyncio
async def test_college_search_with_results(mock_dao: dict) -> None:
    mock_dao["search"].return_value = [
        {"id": "C001", "name": "清华大学", "province": "北京", "city": "北京",
         "type": "综合", "level": "985+211+双一流", "is_public": 1,
         "employment_rate": 0.98, "avg_salary": 25000},
    ]
    tool = CollegeSearchTool()
    result = await tool.execute(province="北京")
    assert result.success
    assert "清华大学" in result.content
    assert "985" in result.content


@pytest.mark.asyncio
async def test_college_search_uses_default_limit(mock_dao: dict) -> None:
    tool = CollegeSearchTool()
    await tool.execute(province="广东")
    assert mock_dao["search"].call_args[1].get("limit", 50) == 50


@pytest.mark.asyncio
async def test_volunteer_score_definition() -> None:
    tool = VolunteerScoreTool()
    defn = tool.get_definition()
    assert defn.name == "volunteer_score"
    assert any(p.name == "college_id" for p in defn.parameters)


@pytest.mark.asyncio
async def test_volunteer_score_college_not_found(mock_dao: dict) -> None:
    mock_dao["detail"].return_value = None
    tool = VolunteerScoreTool()
    result = await tool.execute(college_id="NONEXIST")
    assert result.success


@pytest.mark.asyncio
async def test_volunteer_score_with_detail(mock_dao: dict) -> None:
    mock_dao["detail"].return_value = {
        "id": "C001",
        "name": "清华大学",
        "dorm_score": 9.0,
        "city_vitality": 9.0,
        "cost_index": 3.0,
        "employment_rate": 0.98,
        "avg_salary": 25000,
        "majors": [
            {"id": "M001", "name": "计算机科学与技术",
             "min_rank_2024": 50, "min_rank_2023": 55, "min_rank_2022": 60},
        ],
    }
    mock_dao["score"].return_value = {
        "total_score": 0.85,
        "detail_scores": {
            "academic_fit": 0.6, "admission_prob": 0.8,
            "dorm_quality": 0.9, "city_vitality": 0.9,
            "cost_efficiency": 0.5, "employment": 0.9, "career_alignment": 0.5,
        },
        "explanations": {},
    }
    tool = VolunteerScoreTool()
    result = await tool.execute(college_id="C001", major_id="M001", user_rank="100")
    assert result.success
    assert "0.85" in result.content or "85" in result.content


@pytest.mark.asyncio
async def test_volunteer_recommend_definition() -> None:
    tool = VolunteerRecommendTool()
    defn = tool.get_definition()
    assert defn.name == "volunteer_recommend"


@pytest.mark.asyncio
async def test_volunteer_recommend_no_colleges(mock_dao: dict) -> None:
    mock_dao["search"].return_value = []
    tool = VolunteerRecommendTool()
    result = await tool.execute(user_rank="5000")
    assert result.success


@pytest.mark.asyncio
async def test_volunteer_recommend_with_tiers(mock_dao: dict) -> None:
    mock_dao["search"].return_value = [
        {"id": "C001", "name": "清华", "dorm_score": 9, "city_vitality": 9,
         "cost_index": 3, "employment_rate": 0.98, "avg_salary": 25000},
    ]
    mock_dao["recommend"].return_value = {
        "recommendations": [
            {"college": {"id": "C001", "name": "清华大学"}, "total_score": 0.9,
             "detail_scores": {"admission_prob": 0.3}},
        ],
        "tiers": {
            "reach": [{"college": {"id": "C001", "name": "清华大学"}, "total_score": 0.9}],
            "steady": [],
            "safe": [],
        },
    }
    tool = VolunteerRecommendTool()
    result = await tool.execute(user_rank="5000", province="北京")
    assert result.success
