from __future__ import annotations

from deeptutor.services.custom.admission_dao import (
    bulk_import_ranks,
    get_admission_ranks,
    import_admission_rank,
    search_admission_ranks,
)


def test_get_admission_ranks(custom_db: None) -> None:
    rows = get_admission_ranks("C001", "M001", "广东")
    assert len(rows) == 2
    years = sorted(r["year"] for r in rows)
    assert years == [2024, 2025]


def test_get_admission_ranks_no_data(custom_db: None) -> None:
    rows = get_admission_ranks("NONEXIST", "M001", "广东")
    assert rows == []


def test_search_admission_ranks_by_province(custom_db: None) -> None:
    rows = search_admission_ranks(province="广东")
    assert len(rows) == 4
    for r in rows:
        assert r["province"] == "广东"


def test_search_admission_ranks_by_college(custom_db: None) -> None:
    rows = search_admission_ranks(college_id="C001")
    assert len(rows) == 2


def test_import_and_retrieve(custom_db: None) -> None:
    import_admission_rank("C002", "M001", "北京", 2024, min_rank=10, min_score=700)
    rows = get_admission_ranks("C002", "M001", "北京")
    assert len(rows) == 1
    assert rows[0]["min_rank"] == 10


def test_bulk_import(custom_db: None) -> None:
    records = [
        {"college_id": "C002", "major_id": "M001", "province": "上海", "year": 2024, "min_rank": 100, "min_score": 650},
        {"college_id": "C002", "major_id": "M002", "province": "上海", "year": 2024, "min_rank": 200, "min_score": 640},
    ]
    count = bulk_import_ranks(records)
    assert count == 2
