from __future__ import annotations

import pytest

from deeptutor.tools.custom.exam_tools import GapAnalysisTool, StudyDashboardTool, UploadExamTool


@pytest.mark.asyncio
async def test_upload_exam_definition() -> None:
    tool = UploadExamTool()
    defn = tool.get_definition()
    assert defn.name == "upload_exam"
    assert len(defn.parameters) > 0


@pytest.mark.asyncio
async def test_upload_exam_execute_creates_record(mock_dao: dict) -> None:
    tool = UploadExamTool()
    result = await tool.execute(
        user_id="test_user",
        subject="数学",
        score=85,
        total=100,
        weak_points="函数,导数",
        strong_points="代数",
    )
    assert result.success
    assert "85.0%" in result.content
    mock_dao["upload"].assert_called_once()


@pytest.mark.asyncio
async def test_upload_exam_no_score(mock_dao: dict) -> None:
    tool = UploadExamTool()
    result = await tool.execute(user_id="test_user", subject="数学")
    assert result.success


@pytest.mark.asyncio
async def test_upload_exam_empty_weak_points(mock_dao: dict) -> None:
    tool = UploadExamTool()
    result = await tool.execute(
        user_id="test_user", subject="数学", weak_points="",
    )
    assert result.success


@pytest.mark.asyncio
async def test_study_dashboard_definition() -> None:
    tool = StudyDashboardTool()
    defn = tool.get_definition()
    assert defn.name == "study_dashboard"
    assert any(p.name == "user_id" for p in defn.parameters)


@pytest.mark.asyncio
async def test_study_dashboard_empty(mock_dao: dict) -> None:
    mock_dao["timeline"].return_value = []
    mock_dao["summary"].return_value = []
    tool = StudyDashboardTool()
    result = await tool.execute(user_id="test_user")
    assert result.success
    assert "0 条" in result.content or "没有" in result.content


@pytest.mark.asyncio
async def test_study_dashboard_with_data(mock_dao: dict) -> None:
    mock_dao["timeline"].return_value = [
        {"subject": "数学", "score": 85, "total": 100, "record_type": "exam", "created_at": 1700000000},
    ]
    mock_dao["summary"].return_value = [
        {"subject": "数学", "avg_accuracy": 0.85, "count": 1},
    ]
    tool = StudyDashboardTool()
    result = await tool.execute(user_id="test_user")
    assert result.success
    assert "数学" in result.content


@pytest.mark.asyncio
async def test_gap_analysis_definition() -> None:
    tool = GapAnalysisTool()
    defn = tool.get_definition()
    assert defn.name == "gap_analysis"


@pytest.mark.asyncio
async def test_gap_analysis_empty(mock_dao: dict) -> None:
    mock_dao["gap"].return_value = {
        "total_records": 0, "weak_points_ranked": [],
        "strong_points_ranked": [], "suggestion": "暂无数据",
    }
    tool = GapAnalysisTool()
    result = await tool.execute(user_id="test_user")
    assert result.success


@pytest.mark.asyncio
async def test_gap_analysis_with_data(mock_dao: dict) -> None:
    mock_dao["gap"].return_value = {
        "total_records": 2,
        "weak_points_ranked": [
            {"point": "函数", "count": 3},
            {"point": "导数", "count": 2},
        ],
        "strong_points_ranked": [
            {"point": "代数", "count": 2},
        ],
        "suggestion": "建议加强函数和导数的练习",
    }
    tool = GapAnalysisTool()
    result = await tool.execute(user_id="test_user")
    assert result.success
    assert "函数" in result.content
