"""错题本数据层。

辅助学习模块的核心存储：错题/试卷/作业的 AI 分析结果 + 复习记录。
所有函数保持原生 sqlite3（无 ORM），与 `db.py` 约定一致。

数据结构约定：
- `mistakes.knowledge_points` 为 JSON 数组，如 ["函数的单调性", "导数几何意义"]
- `mistakes.mastery` 为 0~1 掌握度（初始 0.3，复习做对累加、做错回落）
- `mistakes.status`: open（待复习）/ mastered（已掌握）/ archived（归档）
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from deeptutor.services.custom.db import get_connection

SOURCE_TYPES = ("mistake", "paper", "homework")
STATUSES = ("open", "mastered", "archived")


def create_mistake(
    user_id: str,
    *,
    source_type: str = "mistake",
    subject: str = "",
    source_text: str = "",
    question: str = "",
    ai_answer: str = "",
    ai_explanation: str = "",
    knowledge_points: list[str] | None = None,
    mistake_reason: str = "",
    difficulty: str = "medium",
    is_mistake: bool = True,
    mastery: float = 0.3,
    status: str = "open",
    created_at: float | None = None,
) -> dict[str, Any]:
    """写入一条错题记录，返回完整字典（含 id）。"""
    if source_type not in SOURCE_TYPES:
        source_type = "mistake"
    if status not in STATUSES:
        status = "open"
    now = created_at or time.time()
    record_id = uuid.uuid4().hex[:12]
    conn = get_connection()
    conn.execute(
        """INSERT INTO mistakes
           (id, user_id, source_type, subject, source_text, question, ai_answer,
            ai_explanation, knowledge_points, mistake_reason, difficulty, is_mistake,
            mastery, review_count, last_reviewed_at, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record_id,
            user_id,
            source_type,
            subject,
            source_text,
            question,
            ai_answer,
            ai_explanation,
            json.dumps(knowledge_points or [], ensure_ascii=False),
            mistake_reason,
            difficulty,
            1 if is_mistake else 0,
            max(0.0, min(1.0, mastery)),
            0,
            None,
            status,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_mistake(record_id) or {"id": record_id, "user_id": user_id}


def get_mistake(mistake_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM mistakes WHERE id = ?", (mistake_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_mistakes(
    user_id: str,
    *,
    subject: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """错题本列表。默认按创建时间倒序（最新在前）。"""
    where = ["user_id = ?"]
    params: list[Any] = [user_id]
    if subject:
        where.append("subject = ?")
        params.append(subject)
    if status in STATUSES:
        where.append("status = ?")
        params.append(status)
    if source_type in SOURCE_TYPES:
        where.append("source_type = ?")
        params.append(source_type)
    params.extend([limit, offset])
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT * FROM mistakes WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_mistake(mistake_id: str, **fields: Any) -> dict[str, Any] | None:
    """部分更新错题字段（question/answer/explanation/knowledge_points/...）。"""
    allowed = {
        "subject", "source_text", "question", "ai_answer", "ai_explanation",
        "knowledge_points", "mistake_reason", "difficulty", "is_mistake",
        "mastery", "status",
    }
    updates: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "knowledge_points":
            value = json.dumps(value or [], ensure_ascii=False)
        elif key == "is_mistake":
            value = 1 if value else 0
        elif key == "mastery":
            value = max(0.0, min(1.0, float(value)))
        updates.append(f"{key} = ?")
        params.append(value)
    if not updates:
        return get_mistake(mistake_id)
    updates.append("updated_at = ?")
    params.append(time.time())
    params.append(mistake_id)
    conn = get_connection()
    conn.execute(f"UPDATE mistakes SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_mistake(mistake_id)


def delete_mistake(mistake_id: str) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM mistakes WHERE id = ?", (mistake_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def add_review(mistake_id: str, user_id: str, performance: bool) -> dict[str, Any] | None:
    """复习打卡：performance=True 表示本次做对。

    掌握度更新规则（简单遗忘曲线）：
      - 做对: mastery = min(1.0, mastery + 0.2 + 0.1 * log2(review_count + 1))
      - 做错: mastery = max(0.05, mastery - 0.25)
    连续 3 次做对自动标记为 mastered（仍可在列表中出现）。
    """
    mistake = get_mistake(mistake_id)
    if mistake is None:
        return None
    now = time.time()
    conn = get_connection()
    conn.execute(
        "INSERT INTO mistake_reviews (mistake_id, user_id, performance, created_at) VALUES (?,?,?,?)",
        (mistake_id, user_id, 1 if performance else 0, now),
    )
    review_count = mistake.get("review_count", 0) + 1
    mastery = float(mistake.get("mastery", 0.3))
    if performance:
        mastery = min(1.0, mastery + 0.2 + 0.1 * (review_count - 1) * 0.5)
    else:
        mastery = max(0.05, mastery - 0.25)
    status = mistake.get("status", "open")
    if status != "archived" and review_count >= 3 and mastery >= 0.8:
        status = "mastered"
    conn.execute(
        """UPDATE mistakes
           SET mastery = ?, review_count = ?, last_reviewed_at = ?, status = ?, updated_at = ?
           WHERE id = ?""",
        (mastery, review_count, now, status, now, mistake_id),
    )
    conn.commit()
    conn.close()
    return get_mistake(mistake_id)


def get_mistake_stats(user_id: str) -> dict[str, Any]:
    """错题本统计：总量 / 按科目 / 按状态 / 按难度 / 薄弱知识点 Top。"""
    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM mistakes WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]

    by_subject = [
        dict(r)
        for r in conn.execute(
            """SELECT subject, COUNT(*) AS count,
                      AVG(mastery) AS avg_mastery,
                      SUM(CASE WHEN status = 'mastered' THEN 1 ELSE 0 END) AS mastered
               FROM mistakes WHERE user_id = ?
               GROUP BY subject ORDER BY count DESC""",
            (user_id,),
        ).fetchall()
    ]
    by_status = {
        r["status"]: r["count"]
        for r in conn.execute(
            "SELECT status, COUNT(*) AS count FROM mistakes WHERE user_id = ? GROUP BY status",
            (user_id,),
        ).fetchall()
    }
    by_difficulty = {
        r["difficulty"]: r["count"]
        for r in conn.execute(
            "SELECT difficulty, COUNT(*) AS count FROM mistakes WHERE user_id = ? GROUP BY difficulty",
            (user_id,),
        ).fetchall()
    }

    # 薄弱知识点：出现在错题中且掌握度 < 0.6 的知识点，按 fail 次数降序
    weak_counter: dict[str, dict[str, Any]] = {}
    rows = conn.execute(
        """SELECT knowledge_points, mastery FROM mistakes
           WHERE user_id = ? AND status != 'archived'""",
        (user_id,),
    ).fetchall()
    for r in rows:
        for kp in json.loads(r["knowledge_points"] or "[]"):
            kp = str(kp).strip()
            if not kp:
                continue
            entry = weak_counter.setdefault(kp, {"point": kp, "fail_count": 0, "mastery_sum": 0.0, "count": 0})
            entry["fail_count"] += 1
            entry["mastery_sum"] += float(r["mastery"] or 0.3)
            entry["count"] += 1
    weak_points = []
    for entry in weak_counter.values():
        entry["avg_mastery"] = round(entry["mastery_sum"] / entry["count"], 3)
        if entry["avg_mastery"] < 0.6:
            weak_points.append(entry)
    weak_points.sort(key=lambda x: -x["fail_count"])

    conn.close()
    return {
        "total": total,
        "by_subject": by_subject,
        "by_status": by_status,
        "by_difficulty": by_difficulty,
        "weak_knowledge_points": weak_points[:50],
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["knowledge_points"] = json.loads(d.get("knowledge_points") or "[]")
    d["is_mistake"] = bool(d.get("is_mistake"))
    return d
