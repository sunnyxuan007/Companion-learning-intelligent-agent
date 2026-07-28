from __future__ import annotations

from deeptutor.services.custom.db import get_connection


def init_medical_tables() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS medical_restrictions (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            severity TEXT DEFAULT 'medium'
        );
        CREATE TABLE IF NOT EXISTS major_medical_restrictions (
            major_id TEXT NOT NULL,
            restriction_code TEXT NOT NULL REFERENCES medical_restrictions(code),
            PRIMARY KEY (major_id, restriction_code)
        );
    """)
    conn.commit()
    conn.close()


def seed_default_restrictions() -> None:
    from deeptutor.services.custom.student_profile import MEDICAL_RESTRICTION_MAP, RESTRICTION_AFFECTED_MAJORS
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM medical_restrictions").fetchone()[0]
    if existing > 0:
        conn.close()
        return
    cur = conn.cursor()
    for code, desc in MEDICAL_RESTRICTION_MAP.items():
        cur.execute(
            "INSERT OR IGNORE INTO medical_restrictions (code, description, severity) VALUES (?, ?, ?)",
            (code, desc, "high" if code.startswith("4") else "medium"),
        )
    for code, major_ids in RESTRICTION_AFFECTED_MAJORS.items():
        for mid in major_ids:
            cur.execute(
                "INSERT OR IGNORE INTO major_medical_restrictions (major_id, restriction_code) VALUES (?, ?)",
                (mid, code),
            )
    conn.commit()
    conn.close()


def get_restrictions_by_major(major_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.code, r.description
        FROM medical_restrictions r
        JOIN major_medical_restrictions m ON r.code = m.restriction_code
        WHERE m.major_id = ?
    """, (major_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_restrictions() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT code, description, severity FROM medical_restrictions ORDER BY code").fetchall()
    conn.close()
    return [dict(r) for r in rows]
