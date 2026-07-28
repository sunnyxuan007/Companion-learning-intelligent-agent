from __future__ import annotations

import time
from typing import Any

from deeptutor.services.custom.db import get_connection


def search_advisors(
    school: str | None = None,
    college_name: str | None = None,
    name: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = get_connection()
    conditions: list[str] = []
    params: list[Any] = []
    if school:
        conditions.append("school LIKE ?")
        params.append(f"%{school}%")
    if college_name:
        conditions.append("college LIKE ?")
        params.append(f"%{college_name}%")
    if name:
        conditions.append("name LIKE ?")
        params.append(f"%{name}%")
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM advisor_evaluations WHERE {where} ORDER BY score DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_advisor_stats(
    school: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    conn = get_connection()
    conditions: list[str] = []
    params: list[Any] = []
    if school:
        conditions.append("school LIKE ?")
        params.append(f"%{school}%")
    if name:
        conditions.append("name LIKE ?")
        params.append(f"%{name}%")
    where = " AND ".join(conditions) if conditions else "1=1"
    row = conn.execute(
        f"""SELECT COUNT(*) as count, AVG(score) as avg_score,
                  MIN(score) as min_score, MAX(score) as max_score
           FROM advisor_evaluations WHERE {where}""",
        params,
    ).fetchone()
    conn.close()
    return dict(row) if row else {"count": 0}


def import_evaluation(
    school: str,
    college: str | None,
    name: str,
    score: float,
    review_text: str | None,
) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO advisor_evaluations (school, college, name, score, review_text, created_at) VALUES (?,?,?,?,?,?)",
        (school, college, name, score, review_text, time.time()),
    )
    conn.commit()
    conn.close()


def bulk_import(evaluations: list[dict[str, Any]]) -> int:
    conn = get_connection()
    count = 0
    for ev in evaluations:
        try:
            conn.execute(
                "INSERT INTO advisor_evaluations (school, college, name, score, review_text, created_at) VALUES (?,?,?,?,?,?)",
                (
                    ev.get("school", ""),
                    ev.get("college"),
                    ev.get("name", ""),
                    float(ev.get("score", 0)),
                    ev.get("review_text"),
                    time.time(),
                ),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count
