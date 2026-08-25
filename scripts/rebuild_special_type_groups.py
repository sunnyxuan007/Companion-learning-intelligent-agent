"""重建特殊类型招生组号：2026 目录组号为展示单位 + 2025 院校级位次 + 2026 计划。

背景（AGENTS.md Phase 23.4）：2025 特殊类型投档组号（g702/g704/g706…）与 2026 目录
组号（g701-704，每校重新编号）完全重构（如北大 2025 g705 → 2026 g701/g702；
中山 2025 g710/711/715 → 2026 g701-704）。评分引擎 pool（year<2026 位次）用 2025 组号
匹配不上 2026 专业行（g701-704）→ 特殊类型组缺专业明细。

方案（数据层重建，评分引擎零改动）：
1. 展示单位 = 2026 特殊类型 GEN 组（g701-704，计划数取 2026）
2. 位次 = 每校 2025 特殊类型院校级最低位次（组号重构无法精确到组，特殊类型院校自主录取）
3. 为每个 2026 组写 year=2025 mapped 行（2026 组号 + 2025 院校位次 + 2026 计划数）
4. 删除 2025 特殊类型 GEN 旧组行（g7xx 重构前）
幂等：重复运行无副作用。

用法：python scripts/rebuild_special_type_groups.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

BATCH = "提前批本科-特殊类型招生"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(get_custom_db_path())
    conn.row_factory = sqlite3.Row

    # 1. 2026 特殊类型 GEN 组（展示单位，含 2026 计划数）
    gen26 = []
    for r in conn.execute(
        """SELECT college_id, group_code, exam_category, enrollment_count, min_score
           FROM admission_ranks
           WHERE province='广东' AND year=2026 AND batch=? AND major_id='GEN'""",
        (BATCH,),
    ).fetchall():
        gen26.append(dict(r))
    print(f"2026 特殊类型 GEN 组: {len(gen26)}（物理 {sum(1 for g in gen26 if g['exam_category']=='物理')} + 历史 {sum(1 for g in gen26 if g['exam_category']=='历史')}）")

    # 2. 每校 2025 特殊类型院校级位次（跨科类取 MIN——特殊类型院校自主录取，
    #    2025/2026 科类归属可漂移，如北大 2025 归历史、2026 归物理+历史）
    school_rank: dict[str, tuple[int, int]] = {}
    for r in conn.execute(
        """SELECT college_id, MIN(min_rank) AS best_rank, MAX(min_score) AS best_score
           FROM admission_ranks
           WHERE province='广东' AND year=2025 AND batch=? AND major_id='GEN' AND min_rank>0
           GROUP BY college_id""",
        (BATCH,),
    ).fetchall():
        school_rank[r["college_id"]] = (int(r["best_rank"]), int(r["best_score"] or 0))

    # 3. 检查 2026 组是否已有 mapped 行（幂等）
    existing = set()
    for r in conn.execute(
        """SELECT college_id, group_code, exam_category FROM admission_ranks
           WHERE province='广东' AND year=2025 AND batch=? AND rank_source='mapped'""",
        (BATCH,),
    ).fetchall():
        existing.add((r["college_id"], r["group_code"], r["exam_category"]))

    written = 0
    no_rank = 0
    for g in gen26:
        rk = school_rank.get(g["college_id"])
        if not rk:
            no_rank += 1
            continue
        plan = int(g["enrollment_count"] or 0)
        rank25, score25 = rk
        if (g["college_id"], g["group_code"], g["exam_category"]) in existing:
            continue
        if not args.dry_run:
            conn.execute(
                """INSERT OR IGNORE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score,
                    enrollment_count, exam_category, group_code, rank_source, art_category)
                   VALUES (?, 'GEN', '广东', 2025, ?, ?, ?, ?, ?, ?, 'mapped', '')""",
                (g["college_id"], BATCH, rank25, score25, plan, g["exam_category"], g["group_code"]),
            )
        written += 1

    # 4. 删除 2025 特殊类型 GEN 旧组行（重构前组号，非 mapped）
    if not args.dry_run:
        cur = conn.execute(
            """DELETE FROM admission_ranks
               WHERE province='广东' AND year=2025 AND batch=?
                 AND major_id='GEN' AND (rank_source IS NULL OR rank_source='' OR rank_source='official')""",
            (BATCH,),
        )
        deleted = cur.rowcount
        conn.commit()
    else:
        deleted = conn.execute(
            """SELECT COUNT(*) FROM admission_ranks
               WHERE province='广东' AND year=2025 AND batch=?
                 AND major_id='GEN' AND (rank_source IS NULL OR rank_source='' OR rank_source='official')""",
            (BATCH,),
        ).fetchone()[0]
        deleted = int(deleted)

    print(f"新建 mapped 行: {written} | 无2025位次跳过: {no_rank} | 删除旧2025 GEN组: {deleted}")
    if args.dry_run:
        print("(--dry-run 未写入)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
