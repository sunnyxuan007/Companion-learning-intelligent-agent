from __future__ import annotations

import pytest

from deeptutor.services.custom.study_dao import (
    get_gap_analysis,
    get_study_timeline,
    get_subject_summary,
    upload_study_record,
)
from deeptutor.services.custom.models import StudyRecord


def test_upload_study_record_auto_generates_id(custom_db: None) -> None:
    record = StudyRecord(
        id="",
        user_id="user1",
        record_type="exam",
        subject="物理",
        score=90,
        total=100,
        weak_points=["力学"],
        strong_points=["电学"],
    )
    upload_study_record(record)
    timeline = get_study_timeline("user1", days=365)
    subjects = [r["subject"] for r in timeline]
    assert "物理" in subjects


def test_upload_study_record_without_score(custom_db: None) -> None:
    record = StudyRecord(
        id="",
        user_id="user1",
        record_type="note",
        subject="化学",
        title="笔记",
    )
    upload_study_record(record)
    timeline = get_study_timeline("user1", days=365)
    subjects = [r["subject"] for r in timeline]
    assert "化学" in subjects


def test_get_study_timeline_respects_days(custom_db: None) -> None:
    timeline = get_study_timeline("user1", days=1)
    assert len(timeline) == 0


def test_get_subject_summary(custom_db: None) -> None:
    summary = get_subject_summary("user1")
    assert len(summary) == 2
    subjects = {r["subject"] for r in summary}
    assert subjects == {"数学", "英语"}


def test_get_subject_summary_accuracy(custom_db: None) -> None:
    summary = get_subject_summary("user1", subject="数学")
    assert len(summary) == 1
    accuracy = summary[0]["avg_accuracy"]
    assert accuracy == pytest.approx(0.815, rel=0.01)


def test_get_subject_summary_no_records(custom_db: None) -> None:
    summary = get_subject_summary("nobody")
    assert summary == []


def test_get_gap_analysis(custom_db: None) -> None:
    analysis = get_gap_analysis("user1")
    assert "weak_points_ranked" in analysis
    assert "suggestion" in analysis
    weak = analysis["weak_points_ranked"]
    assert len(weak) > 0
    assert weak[0]["point"] in ("函数", "导数", "积分")


def test_get_gap_analysis_by_subject(custom_db: None) -> None:
    analysis = get_gap_analysis("user1", subject="数学")
    weak = [w["point"] for w in analysis["weak_points_ranked"]]
    assert "函数" in weak
    assert "积分" in weak


def test_get_gap_analysis_empty(custom_db: None) -> None:
    analysis = get_gap_analysis("nobody")
    assert analysis["weak_points_ranked"] == []
    assert analysis["strong_points_ranked"] == []
    assert analysis["suggestion"] != ""
