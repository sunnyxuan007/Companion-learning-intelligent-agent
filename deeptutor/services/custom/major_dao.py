from __future__ import annotations

import json
from typing import Any

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.models import Major


def search_majors(
    category: str | None = None,
    subject_group: str | None = None,
    keyword: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = get_connection()
    conditions: list[str] = []
    params: list[Any] = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if subject_group:
        conditions.append("subject_group = ?")
        params.append(subject_group)
    if keyword:
        conditions.append("name LIKE ?")
        params.append(f"%{keyword}%")
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM majors WHERE {where} ORDER BY category, name LIMIT ?",
        [*params, limit],
    ).fetchall()
    conn.close()
    return [_parse_major_row(r) for r in rows]


def get_major_detail(major_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM majors WHERE id = ?", (major_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _parse_major_row(row)


def get_majors_by_subject(exam_category: str) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM majors WHERE subject_group = ? OR subject_group IS NULL ORDER BY category, name",
        (exam_category,),
    ).fetchall()
    conn.close()
    return [_parse_major_row(r) for r in rows]


def import_major(major: Major) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO majors
           (id, name, category, subject_group, description, career_paths,
            course_intro, graduate_directions, salary_range, discipline_evaluation)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            major.id,
            major.name,
            major.category,
            major.subject_group,
            major.description,
            json.dumps(major.career_paths, ensure_ascii=False),
            major.course_intro,
            json.dumps(major.graduate_directions, ensure_ascii=False),
            major.salary_range,
            major.discipline_evaluation,
        ),
    )
    conn.commit()
    conn.close()


def _parse_major_row(row: Any) -> dict[str, Any]:
    d = dict(row)
    for field in ("career_paths", "graduate_directions"):
        if isinstance(d.get(field), str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
