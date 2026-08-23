"""修复提前批专业明细缺失：恢复 2026 计划专业行 + 2025 官方位次映射到 2026 组号。

背景（AGENTS.md Phase 23.2）：官方 2025 提前批投档表只有组级位次（GEN，2025 组号）；
2026 招生计划（专业明细）在专家版 Excel 中（官方 2026 组号，与 2026 目录一致）。
部分院校组号逐年变动（如北电院 2025: 103/104 → 2026: 101/102）。

步骤：
1. 从备份库恢复 2026 提前批专业行（非军检/卫生/教师——导入官方位次时被删）
2. 2025 官方 GEN 组号 → 2026 组号映射：
   a. 2026 已存在同组号 → 保持
   b. 组号变动 → 用备份中 Excel 2025 GEN（同位次+同计划数，唯一）找稳定组号，
      新建 year=2025 GEN 行（2026 组号 + 官方位次，rank_source='mapped'），删除旧 2025 GEN
3. 幂等：重复运行无副作用

用法：python scripts/fix_advance_groups.py [--dry-run] [--backup PATH]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

BATCHES_OFFICIAL_2025 = (
    "提前批本科-军检类",
    "提前批本科-非军检类",
    "提前批本科-特殊类型招生",
    "提前批本科-空军海军招飞",
)
BATCHES_RESTORE_MAJORS = (
    "提前批本科-非军检类",
    "提前批本科-卫生专项",
    "提前批本科-教师专项",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", default="data/user/custom/deeptutor_custom.db.bak_before_official_ranks_20260823_000717")
    args = ap.parse_args()

    db = get_custom_db_path()
    bak = Path(args.backup)
    if not bak.is_absolute():
        bak = Path(__file__).resolve().parent.parent / bak

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    bconn = sqlite3.connect(f"file:{bak}?mode=ro", uri=True)
    bconn.row_factory = sqlite3.Row

    # 1. 恢复 2026 专业行（备份 → 当前）
    restored = 0
    for batch in BATCHES_RESTORE_MAJORS:
        for r in bconn.execute(
            """SELECT * FROM admission_ranks WHERE province='广东' AND year=2026
               AND batch=? AND major_id!='GEN' AND group_code!=''""",
            (batch,),
        ).fetchall():
            d = dict(r)
            if not args.dry_run:
                conn.execute(
                    """INSERT OR IGNORE INTO admission_ranks
                       (college_id, major_id, province, year, batch, min_rank, min_score,
                        enrollment_count, exam_category, group_code, rank_source, art_category)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (d["college_id"], d["major_id"], d["province"], d["year"], d["batch"],
                     d["min_rank"], d["min_score"], d["enrollment_count"], d["exam_category"],
                     d["group_code"], d["rank_source"] or "excel", d["art_category"] or ""),
                )
            restored += 1

    # 2026 已有组号集合（用于映射判断）
    g26: set[tuple[str, str]] = set()
    for r in conn.execute(
        """SELECT DISTINCT college_id, group_code FROM admission_ranks
           WHERE province='广东' AND year=2026 AND batch LIKE '提前批本科%' AND group_code!=''"""
    ).fetchall():
        g26.add((r["college_id"], r["group_code"]))

    # 2. 组号映射
    remapped = 0
    kept = 0
    unresolved = 0
    for batch in BATCHES_OFFICIAL_2025:
        rows = conn.execute(
            """SELECT college_id, group_code, min_rank, enrollment_count, exam_category FROM admission_ranks
               WHERE province='广东' AND year=2025 AND major_id='GEN' AND min_rank>0 AND batch=?""",
            (batch,),
        ).fetchall()
        for r in rows:
            cid, code25, rank, plan, cat = (
                r["college_id"], r["group_code"], r["min_rank"], r["enrollment_count"], r["exam_category"],
            )
            if (cid, code25) in g26:
                kept += 1
                continue
            # 备份中 Excel 2025 GEN：位次相同（唯一）→ 稳定组号；计划数作容差校验
            cands = bconn.execute(
                """SELECT group_code, enrollment_count FROM admission_ranks
                   WHERE province='广东' AND year=2025 AND major_id='GEN' AND min_rank=?
                     AND college_id=? AND exam_category=? AND batch LIKE '提前批本科%'""",
                (rank, cid, cat),
            ).fetchall()
            codeE = None
            if len(cands) == 1:
                tol = max(2, int(plan or 0) // 10)
                if abs(int(cands[0]["enrollment_count"] or 0) - int(plan or 0)) <= tol:
                    codeE = cands[0]["group_code"]
            if codeE is None and len(cands) == 1:
                # 计划数口径差异较大但位次唯一 → 仍采信位次
                codeE = cands[0]["group_code"]
            if codeE is None:
                # 计划数唯一匹配（容差）
                by_plan = bconn.execute(
                    """SELECT group_code FROM admission_ranks
                       WHERE province='广东' AND year=2025 AND major_id='GEN'
                         AND college_id=? AND exam_category=? AND batch LIKE '提前批本科%'
                         AND ABS(enrollment_count - ?) <= ?""",
                    (cid, cat, plan, max(2, int(plan or 0) // 10)),
                ).fetchall()
                if len(by_plan) == 1:
                    codeE = by_plan[0]["group_code"]
            if not codeE or (cid, codeE) not in g26:
                unresolved += 1
                continue
            remapped += 1
            if not args.dry_run:
                conn.execute(
                    """INSERT OR IGNORE INTO admission_ranks
                       (college_id, major_id, province, year, batch, min_rank, min_score,
                        enrollment_count, exam_category, group_code, rank_source, art_category)
                       VALUES (?, 'GEN', '广东', 2025, ?, ?, 0.0, ?, ?, ?, 'mapped', '')""",
                    (cid, batch, rank, plan, cat, codeE),
                )
                # 删除旧 2025 官方组号行（含专业行，若有）
                conn.execute(
                    "DELETE FROM admission_ranks WHERE province='广东' AND year=2025 AND batch=? AND college_id=? AND group_code=?",
                    (batch, cid, code25),
                )

    if not args.dry_run:
        conn.commit()
    bconn.close()
    conn.close()

    print(f"恢复 2026 专业行: {restored}")
    print(f"2025 GEN 组号: 保持 {kept} | 映射到 2026 组号 {remapped} | 未解决 {unresolved}")
    if args.dry_run:
        print("(--dry-run 未写入)")
    return 0


if __name__ == "__main__":
    sys.exit(main())