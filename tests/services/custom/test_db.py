from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from deeptutor.services.custom.db import get_connection, get_custom_db_path, init_db


def test_get_custom_db_path_returns_path(tmp_path: Path) -> None:
    path = get_custom_db_path()
    assert isinstance(path, Path)
    assert path.name == "deeptutor_custom.db"


def test_init_db_creates_all_tables(custom_db: None) -> None:
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in tables]
    assert "colleges" in names
    assert "majors" in names
    assert "college_majors" in names
    assert "study_records" in names
    assert "advisor_evaluations" in names
    conn.close()


def test_init_db_is_idempotent(custom_db: None) -> None:
    init_db()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    assert len(tables) >= 5
    conn.close()


def test_init_db_creates_indexes(custom_db: None) -> None:
    conn = get_connection()
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in indexes]
    assert "idx_college_majors_college" in names
    assert "idx_college_majors_major" in names
    assert "idx_study_records_user" in names
    assert "idx_study_records_subject" in names
    assert "idx_advisor_school" in names
    assert "idx_advisor_name" in names
    conn.close()


def test_connection_has_row_factory(custom_db: None) -> None:
    conn = get_connection()
    assert conn.row_factory is sqlite3.Row
    conn.close()


def test_foreign_keys_enforced(custom_db: None) -> None:
    conn = get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO college_majors (college_id, major_id) VALUES ('NONEXIST', 'M001')"
        )
        conn.commit()
    conn.close()


def test_seed_data_persists(custom_db: None) -> None:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM colleges").fetchone()
    assert row["cnt"] == 5
    row = conn.execute("SELECT COUNT(*) as cnt FROM advisor_evaluations").fetchone()
    assert row["cnt"] == 4
    conn.close()
