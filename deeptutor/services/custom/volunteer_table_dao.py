from __future__ import annotations

import json
import time
import uuid
from typing import Any

from deeptutor.services.custom.db import get_connection

TRASH_RETENTION_SECONDS = 7 * 24 * 3600


def create_plan(
    user_id: str,
    province: str,
    exam_category: str,
    rank: int,
    province_rules: dict[str, Any],
    slots: list[dict[str, Any]],
    batch: str = "本科批",
    score: float | None = None,
    medical_restrictions: list[str] | None = None,
) -> dict[str, Any]:
    now = time.time()
    plan_id = str(uuid.uuid4())
    conn = get_connection()
    conn.execute(
        """INSERT INTO volunteer_plans (id, user_id, province, exam_category, rank, province_rules, slots, status, batch, score, medical_restrictions, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id,
            user_id,
            province,
            exam_category,
            rank,
            json.dumps(province_rules, ensure_ascii=False),
            json.dumps(slots, ensure_ascii=False),
            "draft",
            batch,
            score,
            json.dumps(medical_restrictions or [], ensure_ascii=False),
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


def soft_delete_plan(plan_id: str) -> bool:
    conn = get_connection()
    now = time.time()
    cur = conn.execute(
        "UPDATE volunteer_plans SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
        (now, now, plan_id),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def restore_plan(plan_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    now = time.time()
    conn.execute(
        "UPDATE volunteer_plans SET deleted_at = NULL, updated_at = ? WHERE id = ? AND deleted_at IS NOT NULL",
        (now, plan_id),
    )
    conn.commit()
    conn.close()
    return get_plan(plan_id)


def purge_plan(plan_id: str) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM volunteer_plans WHERE id = ?", (plan_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_plan(plan_id: str) -> bool:
    """兼容旧调用：直接永久删除。"""
    return purge_plan(plan_id)


def list_plans(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """活跃方案（未删除），按创建时间倒序。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM volunteer_plans WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_trash(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """回收站方案（软删除且未超保留期），按删除时间倒序；顺带惰性清理过期项。"""
    conn = get_connection()
    now = time.time()
    cutoff = now - TRASH_RETENTION_SECONDS
    conn.execute(
        "DELETE FROM volunteer_plans WHERE deleted_at IS NOT NULL AND deleted_at < ?",
        (cutoff,),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT * FROM volunteer_plans WHERE user_id = ? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def find_duplicate(
    user_id: str,
    slots: list[dict[str, Any]],
    rank: int | None = None,
    exam_category: str | None = None,
) -> dict[str, Any] | None:
    """在活跃方案中查找内容完全一致（保留顺序，顺序不同即不同）的方案。

    身份判定 = slots + rank（+exam_category）。rank 不同视为不同方案
    （同一份志愿但不同位次场景可并存）。返回命中的方案 dict（含
    created_at 供前端命名），无则 None。
    """
    target = json.dumps(slots, ensure_ascii=False)
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM volunteer_plans WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    for r in rows:
        if json.dumps(json.loads(r["slots"]), ensure_ascii=False) != target:
            continue
        if rank is not None and int(r["rank"] or 0) != rank:
            continue
        if exam_category is not None and r["exam_category"] != exam_category:
            continue
        return _row_to_dict(r)
    return None


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["province_rules"] = json.loads(d["province_rules"])
    d["slots"] = json.loads(d["slots"])
    d["medical_restrictions"] = json.loads(d.get("medical_restrictions") or "[]")
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
        """INSERT INTO volunteer_plans (id, user_id, province, exam_category, rank, province_rules, slots, status, batch, score, medical_restrictions, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            new_id,
            new_user_id,
            original["province"],
            original["exam_category"],
            original["rank"],
            json.dumps(original["province_rules"], ensure_ascii=False),
            json.dumps(slots, ensure_ascii=False),
            "draft",
            original.get("batch", "本科批"),
            original.get("score"),
            json.dumps(original.get("medical_restrictions") or [], ensure_ascii=False),
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
