from __future__ import annotations

import json
import time
import uuid
from typing import Any

from deeptutor.services.custom.db import get_connection


def create_plan(
    user_id: str,
    province: str,
    exam_category: str,
    rank: int,
    province_rules: dict[str, Any],
    slots: list[dict[str, Any]],
) -> dict[str, Any]:
    now = time.time()
    plan_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        """INSERT INTO volunteer_plans (id, user_id, province, exam_category, rank, province_rules, slots, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id,
            user_id,
            province,
            exam_category,
            rank,
            json.dumps(province_rules, ensure_ascii=False),
            json.dumps(slots, ensure_ascii=False),
            "draft",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_plan(plan_id)


def get_plan(plan_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM volunteer_plans WHERE id = ?", (plan_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def update_plan(plan_id: str, slots: list[dict[str, Any]], status: str | None = None) -> dict[str, Any] | None:
    conn = get_connection()
    now = time.time()
    if status:
        conn.execute(
            "UPDATE volunteer_plans SET slots = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(slots, ensure_ascii=False), status, now, plan_id),
        )
    else:
        conn.execute(
            "UPDATE volunteer_plans SET slots = ?, updated_at = ? WHERE id = ?",
            (json.dumps(slots, ensure_ascii=False), now, plan_id),
        )
    conn.commit()
    conn.close()
    return get_plan(plan_id)


def delete_plan(plan_id: str) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM volunteer_plans WHERE id = ?", (plan_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def list_plans(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM volunteer_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["province_rules"] = json.loads(d["province_rules"])
    d["slots"] = json.loads(d["slots"])
    return d


def clone_plan(plan_id: str, new_user_id: str, name: str | None = None) -> dict[str, Any] | None:
    original = get_plan(plan_id)
    if not original:
        return None
    now = time.time()
    new_id = str(uuid.uuid4())
    slots = original["slots"]
    if name:
        for s in slots:
            s["reason"] = f"{name} — {s.get('reason', '')}"
    conn = get_connection()
    conn.execute(
        """INSERT INTO volunteer_plans (id, user_id, province, exam_category, rank, province_rules, slots, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            new_id,
            new_user_id,
            original["province"],
            original["exam_category"],
            original["rank"],
            json.dumps(original["province_rules"], ensure_ascii=False),
            json.dumps(slots, ensure_ascii=False),
            "draft",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_plan(new_id)


def rename_plan(plan_id: str, name: str) -> dict[str, Any] | None:
    plan = get_plan(plan_id)
    if not plan:
        return None
    now = time.time()
    conn = get_connection()
    conn.execute("UPDATE volunteer_plans SET updated_at = ? WHERE id = ?", (now, plan_id))
    conn.commit()
    conn.close()
    return plan
