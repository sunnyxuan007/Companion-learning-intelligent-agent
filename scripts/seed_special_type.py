"""特殊类型院校分类 seed：按 2026 专业行反推综合评价/高水平运动队。

分类规则：该校 2026 特殊类型专业行中含体育类专业（体育教育/运动训练/运动康复/
社会体育指导与管理/休闲体育等）→ 高水平运动队；否则 → 综合评价。
（体育类专业是高水平运动队招生的标志；综合评价招普通专业。）
写 colleges.special_type 列。

用法：python scripts/seed_special_type.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

BATCH = "提前批本科-特殊类型招生"
SPORT_KW = ("体育", "运动", "休闲", "武术", "体能", "冰雪", "康复")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(get_custom_db_path())
    conn.row_factory = sqlite3.Row

    # 幂等：确保 special_type 列存在（db.py init_db 可能未在此进程调用）
    cols = [r[1] for r in conn.execute("PRAGMA table_info(colleges)").fetchall()]
    if "special_type" not in cols:
        conn.execute("ALTER TABLE colleges ADD COLUMN special_type TEXT DEFAULT ''")
        conn.commit()

    # 每校 2026 特殊类型专业行 → 是否含体育专业
    school_sport: set[str] = set()
    school_has_major: set[str] = set()
    for r in conn.execute(
        """SELECT DISTINCT a.college_id, cmn.major_name FROM admission_ranks a
           LEFT JOIN college_major_name cmn ON a.college_id=cmn.college_id AND a.major_id=cmn.major_id
           WHERE a.province='广东' AND a.batch=? AND a.major_id!='GEN' AND a.year=2026""",
        (BATCH,),
    ).fetchall():
        school_has_major.add(r["college_id"])
        if any(k in (r["major_name"] or "") for k in SPORT_KW):
            school_sport.add(r["college_id"])

    # 覆盖：特殊类型 GEN 组院校（2025+2026）
    gen_schools = set()
    for r in conn.execute(
        """SELECT DISTINCT college_id FROM admission_ranks
           WHERE province='广东' AND batch=? AND major_id='GEN'""",
        (BATCH,),
    ).fetchall():
        gen_schools.add(r["college_id"])

    updates: dict[str, str] = {}
    for cid in gen_schools & school_has_major:
        updates[cid] = "高水平运动队" if cid in school_sport else "综合评价"

    print(f"特殊类型院校: {len(gen_schools)} | 能分类(有2026专业行): {len(updates)}")
    from collections import Counter
    print("  分类:", dict(Counter(updates.values())))

    names = {r["id"]: r["name"] for r in conn.execute("SELECT id,name FROM colleges").fetchall()}
    for t in ("综合评价", "高水平运动队"):
        lst = [names.get(c, c) for c, v in sorted(updates.items()) if v == t]
        print(f"  {t} ({len(lst)}): {lst}")

    if not args.dry_run:
        for cid, t in updates.items():
            conn.execute("UPDATE colleges SET special_type=? WHERE id=?", (t, cid))
        conn.commit()
        print(f"已写入 {len(updates)} 所")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
