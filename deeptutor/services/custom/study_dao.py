from __future__ import annotations

import json
import time
import uuid
from typing import Any

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.models import StudyRecord


def upload_study_record(record: StudyRecord) -> None:
    record_id = record.id or uuid.uuid4().hex[:12]
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO study_records
           (id, user_id, record_type, subject, title, content_json,
            score, total, weak_points, strong_points, created_at, exam_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record_id,
            record.user_id,
            record.record_type,
            record.subject,
            record.title,
            "{}",
            record.score,
            record.total,
            json.dumps(record.weak_points, ensure_ascii=False),
            json.dumps(record.strong_points, ensure_ascii=False),
            record.created_at or time.time(),
            time.strftime("%Y-%m-%d", time.localtime(record.created_at or time.time())),
        ),
    )
    conn.commit()
    conn.close()


def get_study_timeline(
    user_id: str, days: int = 30
) -> list[dict[str, Any]]:
    cutoff = time.time() - days * 86400
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM study_records
           WHERE user_id = ? AND created_at >= ?
           ORDER BY created_at DESC""",
        (user_id, cutoff),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["weak_points"] = json.loads(d.get("weak_points", "[]"))
        d["strong_points"] = json.loads(d.get("strong_points", "[]"))
        result.append(d)
    return result


def get_subject_summary(
    user_id: str, subject: str | None = None
) -> list[dict[str, Any]]:
    conn = get_connection()
    if subject:
        rows = conn.execute(
            """SELECT subject,
                      COUNT(*) as count,
                      AVG(CASE WHEN total > 0 THEN score * 1.0 / total ELSE NULL END) as avg_accuracy
               FROM study_records
               WHERE user_id = ? AND subject = ?
               GROUP BY subject""",
            (user_id, subject),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT subject,
                      COUNT(*) as count,
                      AVG(CASE WHEN total > 0 THEN score * 1.0 / total ELSE NULL END) as avg_accuracy
               FROM study_records
               WHERE user_id = ?
               GROUP BY subject""",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_gap_analysis(
    user_id: str, subject: str | None = None
) -> dict[str, Any]:
    records = get_study_timeline(user_id, days=90)
    if subject:
        records = [r for r in records if r["subject"] == subject]
    weak_counter: dict[str, int] = {}
    strong_counter: dict[str, int] = {}
    for r in records:
        for wp in r.get("weak_points", []):
            weak_counter[wp] = weak_counter.get(wp, 0) + 1
        for sp in r.get("strong_points", []):
            strong_counter[sp] = strong_counter.get(sp, 0) + 1
    sorted_weak = sorted(weak_counter.items(), key=lambda x: -x[1])
    sorted_strong = sorted(strong_counter.items(), key=lambda x: -x[1])
    return {
        "total_records": len(records),
        "weak_points_ranked": [
            {"point": k, "count": v} for k, v in sorted_weak
        ],
        "strong_points_ranked": [
            {"point": k, "count": v} for k, v in sorted_strong
        ],
        "suggestion": _generate_suggestion(sorted_weak),
    }


def _generate_suggestion(
    weak_points: list[tuple[str, int]]
) -> str:
    if not weak_points:
        return "暂无明显的薄弱知识点，继续保持当前学习节奏。"
    top = weak_points[:3]
    points_str = "、".join(p for p, _ in top)
    return f"建议优先巩固以下知识点：{points_str}。建议每周安排专项练习，结合错题本反复复习。"
