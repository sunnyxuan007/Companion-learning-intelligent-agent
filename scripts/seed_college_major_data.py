"""
Associate colleges with majors based on college type.

This creates the college_majors table entries so that the scoring
system can match students to college-major pairs.

Each college gets a subset of the ~35 standard majors depending
on its type (综合/理工/师范/医药/etc).
"""

from __future__ import annotations

from deeptutor.services.custom.db import get_connection, init_db
from scripts.seed_major_data import TYPE_MAJOR_MAP


def run():
    init_db()
    conn = get_connection()
    colleges = conn.execute(
        "SELECT id, name, type FROM colleges WHERE id LIKE 'CU%'"
    ).fetchall()

    batch = []
    for row in colleges:
        college_id = row["id"]
        college_type = row["type"] or "综合"
        best_match = college_type
        if best_match not in TYPE_MAJOR_MAP:
            for key in TYPE_MAJOR_MAP:
                if key in best_match or best_match in key:
                    best_match = key
                    break
            else:
                best_match = "综合"

        major_ids = TYPE_MAJOR_MAP.get(best_match, TYPE_MAJOR_MAP["综合"])
        for mid in major_ids:
            batch.append((college_id, mid, "本科批", 4, "学士", 5000))

    conn.executemany(
        """INSERT OR REPLACE INTO college_majors
           (college_id, major_id, batch, years, degree, tuition)
           VALUES (?,?,?,?,?,?)""",
        batch,
    )
    conn.commit()
    conn.close()

    print(f"Associated {len(batch)} college-major pairs ({len(colleges)} colleges).")


if __name__ == "__main__":
    run()
