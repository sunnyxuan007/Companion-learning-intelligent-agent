from __future__ import annotations

import pytest

from deeptutor.services.custom.college_dao import (
    get_college_detail,
    import_college,
    search_colleges,
)
from deeptutor.services.custom.models import College


def test_search_colleges_empty(custom_db: None) -> None:
    results = search_colleges(province="香港")
    assert results == []


def test_search_colleges_by_province(custom_db: None) -> None:
    results = search_colleges(province="广东")
    assert len(results) == 3
    names = [r["name"] for r in results]
    assert "深圳大学" in names
    assert "华南理工大学" in names
    assert "广东工业大学" in names


def test_search_colleges_single_region(custom_db: None) -> None:
    results = search_colleges(regions=["华北"])
    assert len(results) == 2
    names = [r["name"] for r in results]
    assert "清华大学" in names
    assert "北京大学" in names


def test_search_colleges_multiple_regions(custom_db: None) -> None:
    results = search_colleges(regions=["华北", "华南"])
    assert len(results) == 5
    for r in results:
        assert r["region"] in {"华北", "华南"}


def test_search_colleges_region_combined_with_province(custom_db: None) -> None:
    results = search_colleges(regions=["华南"], province="广东")
    assert len(results) == 3
    for r in results:
        assert r["region"] == "华南"
        assert r["province"] == "广东"


def test_search_colleges_by_level(custom_db: None) -> None:
    results = search_colleges(level="985+211+双一流")
    assert len(results) == 3
    for r in results:
        assert "985" in r["level"]


def test_search_colleges_by_keyword(custom_db: None) -> None:
    results = search_colleges(keyword="清华")
    assert len(results) == 1
    assert results[0]["name"] == "清华大学"


def test_search_colleges_combined_filters(custom_db: None) -> None:
    results = search_colleges(province="广东", level="985+211+双一流")
    assert len(results) == 1
    assert results[0]["name"] == "华南理工大学"


def test_search_colleges_limit(custom_db: None) -> None:
    results = search_colleges(province="北京", limit=1)
    assert len(results) == 1


def test_search_colleges_with_type(custom_db: None) -> None:
    results = search_colleges(college_type="理工")
    assert len(results) == 2
    for r in results:
        assert "理工" in (r.get("type") or "")


def test_get_college_detail_found(custom_db: None) -> None:
    detail = get_college_detail("C001")
    assert detail is not None
    assert detail["name"] == "清华大学"
    assert "majors" in detail
    assert len(detail["majors"]) == 2


def test_get_college_detail_not_found(custom_db: None) -> None:
    detail = get_college_detail("NONEXIST")
    assert detail is None


def test_import_college_round_trip(custom_db: None) -> None:
    c = College(
        id="C999",
        name="测试大学",
        province="测试省",
        city="测试市",
    )
    import_college(c)
    results = search_colleges(keyword="测试大学")
    assert len(results) == 1
    assert results[0]["province"] == "测试省"
