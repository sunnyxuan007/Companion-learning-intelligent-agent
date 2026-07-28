from __future__ import annotations

import json
import time
from typing import Any

import sqlite_vec
from deeptutor.services.custom.db import get_connection

from .embed import EMBED_DIM, embed_text


def _vec_rowid(chunk_id: str) -> int:
    return hash(chunk_id) & 0x7FFFFFFFFFFFFFFF


def init_vector_store() -> None:
    conn = get_connection()
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    except Exception:
        pass
    conn.enable_load_extension(False)
    conn.execute(
        f"""CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_v2
           USING vec0(embedding float[{EMBED_DIM}])"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS doc_meta_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT UNIQUE NOT NULL,
            vec_rowid INTEGER UNIQUE NOT NULL,
            source TEXT NOT NULL,
            doc_type TEXT NOT NULL DEFAULT '',
            title TEXT DEFAULT '',
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at REAL NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_meta_v2_vec_rowid ON doc_meta_v2(vec_rowid)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conflict_log_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field TEXT NOT NULL,
            source_a TEXT NOT NULL,
            source_b TEXT NOT NULL,
            value_a TEXT,
            value_b TEXT,
            resolution TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


def add_chunk(
    source: str,
    content: str,
    chunk_id: str | None = None,
    doc_type: str = "",
    title: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    init_vector_store()
    cid = chunk_id or f"chk_{int(time.time() * 1000)}"
    vid = _vec_rowid(cid)
    embedding = embed_text(content)

    conn = get_connection()
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    except Exception:
        pass
    conn.enable_load_extension(False)

    conn.execute(
        "INSERT OR IGNORE INTO doc_chunks_v2(rowid, embedding) VALUES (?, ?)",
        (vid, json.dumps(embedding)),
    )
    conn.execute(
        """INSERT OR REPLACE INTO doc_meta_v2 (chunk_id, vec_rowid, source, doc_type, title, content, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, vid, source, doc_type, title, content, json.dumps(metadata or {}, ensure_ascii=False), time.time()),
    )
    conn.commit()
    conn.close()
    return cid


def search_by_keywords(
    query: str, top_k: int = 3, doc_type: str | None = None
) -> list[dict[str, Any]]:
    """Keyword-based fallback search using SQL LIKE."""
    cleaned = query.replace("?", "").replace("，", " ").replace("、", " ").replace("？", "").replace("。", " ")
    terms = set()
    for w in cleaned.split():
        w = w.strip()
        if not w:
            continue
        if len(w) <= 6:
            terms.add(w)
        else:
            for i in range(len(w) - 1):
                terms.add(w[i:i+2])
    keywords = [t for t in terms if len(t) >= 2]
    if not keywords:
        return []

    conn = get_connection()
    like_clauses = " OR ".join(f"content LIKE ?" for _ in keywords)
    params: list[str] = [f"%{k}%" for k in keywords]
    if doc_type:
        sql = f"SELECT * FROM doc_meta_v2 WHERE ({like_clauses}) AND doc_type=? ORDER BY id LIMIT ?"
        params.append(doc_type)
    else:
        sql = f"SELECT * FROM doc_meta_v2 WHERE {like_clauses} ORDER BY id LIMIT ?"
    params.append(str(top_k * 3))

    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        conn.close()
        return []

    conn.close()

    seen: set[int] = set()
    results: list[dict[str, Any]] = []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        item = dict(r)
        item["distance"] = 0.0
        import json
        item["metadata"] = json.loads(item.get("metadata", "{}"))
        results.append(item)
        if len(results) >= top_k:
            break
    return results


def search_chunks(query_text: str, top_k: int = 5, doc_type: str | None = None) -> list[dict[str, Any]]:
    init_vector_store()
    query_vec = embed_text(query_text)

    conn = get_connection()
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    except Exception:
        pass
    conn.enable_load_extension(False)

    vec_json = json.dumps(query_vec)
    rows = conn.execute(
        f"""SELECT rowid, distance
            FROM doc_chunks_v2
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance""",
        (vec_json, top_k * 3),
    ).fetchall()

    if not rows:
        conn.close()
        return []

    rowids = [r[0] for r in rows]
    placeholders = ",".join("?" for _ in rowids)
    meta_rows = conn.execute(
        f"SELECT * FROM doc_meta_v2 WHERE vec_rowid IN ({placeholders})",
        rowids,
    ).fetchall()

    meta_by_vid = {}
    for r in meta_rows:
        meta_by_vid[r["vec_rowid"]] = r

    results: list[dict[str, Any]] = []
    for row in rows:
        meta = meta_by_vid.get(row[0])
        if not meta:
            continue
        item = dict(meta)
        if doc_type and item.get("doc_type", "") != doc_type:
            continue
        item["distance"] = row[1]
        item["metadata"] = json.loads(item.get("metadata", "{}"))
        results.append(item)
        if len(results) >= top_k:
            break

    conn.close()
    return results


def add_faq(question: str, answer: str, source: str = "faq") -> str:
    content = f"Q: {question}\nA: {answer}"
    return add_chunk(
        source=source,
        content=content,
        chunk_id=f"faq_{int(time.time() * 1000)}",
        doc_type="faq",
        title=question[:80],
        metadata={"question": question},
    )


def log_conflict(
    field: str,
    source_a: str,
    source_b: str,
    value_a: str,
    value_b: str,
    resolution: str = "",
) -> int:
    conn = get_connection()
    conn.execute(
        """INSERT INTO conflict_log_v2 (field, source_a, source_b, value_a, value_b, resolution, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (field, source_a, source_b, value_a, value_b, resolution, time.time()),
    )
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return cid


def delete_source(source: str) -> int:
    conn = get_connection()
    deleted = conn.execute("DELETE FROM doc_meta_v2 WHERE source = ?", (source,)).rowcount
    conn.commit()
    conn.close()
    return deleted
