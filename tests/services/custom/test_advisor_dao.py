from __future__ import annotations

import pytest

from deeptutor.services.custom.advisor_dao import (
    bulk_import,
    get_advisor_stats,
    import_evaluation,
    search_advisors,
)


def test_search_advisors_by_school(custom_db: None) -> None:
    results = search_advisors(school="清华大学")
    assert len(results) == 2
    for r in results:
        assert r["school"] == "清华大学"


def test_search_advisors_by_name(custom_db: None) -> None:
    results = search_advisors(name="王五")
    assert len(results) == 1
    assert results[0]["name"] == "王五"


def test_search_advisors_by_college(custom_db: None) -> None:
    results = search_advisors(college_name="计算机系")
    assert len(results) == 3


def test_search_advisors_empty(custom_db: None) -> None:
    results = search_advisors(school="牛津大学")
    assert results == []


def test_get_advisor_stats(custom_db: None) -> None:
    stats = get_advisor_stats(school="清华大学")
    assert stats["count"] == 2
    assert stats["avg_score"] == pytest.approx(3.75, rel=0.01)


def test_get_advisor_stats_no_match(custom_db: None) -> None:
    stats = get_advisor_stats(school="牛津大学")
    assert stats["count"] == 0


def test_import_and_retrieve(custom_db: None) -> None:
    import_evaluation(
        school="测试大学", college="测试学院", name="测试导师",
        score=4.0, review_text="好评",
    )
    results = search_advisors(school="测试大学")
    assert len(results) == 1
    assert results[0]["score"] == 4.0
    assert results[0]["review_text"] == "好评"


def test_bulk_import(custom_db: None) -> None:
    entries = [
        {"school": "A大", "college": "CS", "name": "t1", "score": 3.0, "review_text": "ok"},
        {"school": "B大", "college": "EE", "name": "t2", "score": 4.0, "review_text": "good"},
    ]
    count = bulk_import(entries)
    assert count == 2
    assert len(search_advisors(school="A大")) == 1


def test_bulk_import_skips_bad_rows(custom_db: None) -> None:
    entries = [
        {"school": "A大", "college": "CS", "name": "t1", "score": 3.0, "review_text": "ok"},
        {"school": "", "college": "", "name": "", "score": "bad", "review_text": None},
    ]
    count = bulk_import(entries)
    assert count == 1
