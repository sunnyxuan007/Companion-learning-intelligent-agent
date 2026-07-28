from __future__ import annotations

from typing import Any

from deeptutor.services.custom.db import get_connection


def add_favorite(user_id: str, item_type: str, item_id: str) -> bool:
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM user_favorites WHERE user_id = ? AND item_type = ? AND item_id = ?",
        (user_id, item_type, item_id),
    ).fetchone()
    if existing:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO user_favorites (user_id, item_type, item_id, created_at) VALUES (?, ?, ?, ?)",
        (user_id, item_type, item_id, __import__("time").time()),
    )
    conn.commit()
    conn.close()
    return True


def remove_favorite(user_id: str, item_type: str, item_id: str) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM user_favorites WHERE user_id = ? AND item_type = ? AND item_id = ?",
        (user_id, item_type, item_id),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_favorites(user_id: str, item_type: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    if item_type:
        rows = conn.execute(
            "SELECT * FROM user_favorites WHERE user_id = ? AND item_type = ? ORDER BY created_at DESC",
            (user_id, item_type),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM user_favorites WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_favorited(user_id: str, item_type: str, item_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM user_favorites WHERE user_id = ? AND item_type = ? AND item_id = ?",
        (user_id, item_type, item_id),
    ).fetchone()
    conn.close()
    return row is not None


def add_browsing_history(user_id: str, item_type: str, item_id: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO browsing_history (user_id, item_type, item_id, viewed_at) VALUES (?, ?, ?, ?)",
        (user_id, item_type, item_id, __import__("time").time()),
    )
    conn.commit()
    conn.close()


def get_browsing_history(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM browsing_history WHERE user_id = ? ORDER BY viewed_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
