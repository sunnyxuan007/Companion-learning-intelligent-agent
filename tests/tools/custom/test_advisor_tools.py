from __future__ import annotations

import pytest

from deeptutor.tools.custom.advisor_tools import AdvisorSearchTool


@pytest.mark.asyncio
async def test_advisor_search_definition() -> None:
    tool = AdvisorSearchTool()
    defn = tool.get_definition()
    assert defn.name == "advisor_search"
    assert any(p.name == "school" for p in defn.parameters)


@pytest.mark.asyncio
async def test_advisor_search_empty(mock_dao: dict) -> None:
    mock_dao["adv_search"].return_value = []
    mock_dao["adv_stats"].return_value = {"count": 0}
    tool = AdvisorSearchTool()
    result = await tool.execute(school="牛津大学")
    assert result.success
    assert "未找到" in result.content


@pytest.mark.asyncio
async def test_advisor_search_with_results(mock_dao: dict) -> None:
    mock_dao["adv_search"].return_value = [
        {"school": "清华大学", "name": "张三", "college": "计算机系",
         "score": 4.5, "review_text": "讲课非常好"},
        {"school": "清华大学", "name": "李四", "college": "计算机系",
         "score": 3.0, "review_text": "一般般"},
    ]
    mock_dao["adv_stats"].return_value = {
        "count": 2, "avg_score": 3.75, "min_score": 3.0, "max_score": 4.5,
    }
    tool = AdvisorSearchTool()
    result = await tool.execute(school="清华大学")
    assert result.success
    assert "张三" in result.content
    assert "4.5" in result.content


@pytest.mark.asyncio
async def test_advisor_search_limit(mock_dao: dict) -> None:
    mock_dao["adv_search"].return_value = [{"school": "A", "name": "X", "score": 4.0}] * 25
    mock_dao["adv_stats"].return_value = {"count": 25, "avg_score": 4.0}
    tool = AdvisorSearchTool()
    result = await tool.execute(name="X")
    assert result.success


@pytest.mark.asyncio
async def test_advisor_search_review_truncation(mock_dao: dict) -> None:
    long_review = "你好 " * 50
    mock_dao["adv_search"].return_value = [
        {"school": "A", "name": "X", "college": None,
         "score": 4.0, "review_text": long_review},
    ]
    mock_dao["adv_stats"].return_value = {"count": 1, "avg_score": 4.0}
    tool = AdvisorSearchTool()
    result = await tool.execute(name="X")
    assert result.success
