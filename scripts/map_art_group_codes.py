"""修复艺体类本科批组号跨年不一致：2025 投档组号 → 2026 目录组号映射。

背景（AGENTS.md Phase 23.x）：艺体类 2025 官方投档只有组级位次（GEN，2025 组号）；
2026 目录专业明细（parse_art_catalog）用 2026 组号。2025 与 2026 组号大量不一致
（如北工大 2025 g204 → 2026 g206），导致评分引擎 pool（2025 组号）JOIN 不上 2026 专业。

方案（复用 fix_advance_groups 的数据层映射模式）：
1. 对每个「2025 有 GEN 位次但 2026 无专业明细」的缺组，用 2026 同校同类别专业组
   的计划数匹配目标组号（Δplan 置信过滤 + 目标组在 2025 无位次的冲突过滤）。
2. 新建 year=2025 GEN 行（2026 组号 + 2025 官方位次，rank_source='mapped'）
3. 删除旧 2025 组号行，使评分引擎 pool 统一用 2026 组号。
幂等：重复运行无副作用。

用法：python scripts/map_art_group_codes.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

BATCH = "艺体类本科批"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(get_custom_db_path())
    conn.row_factory = sqlite3.Row

    # 2025 GEN 缺组（pool 用 year<2026 位次）
    pool = set(
        tuple(r)
        for r in conn.execute(
            """SELECT DISTINCT college_id, group_code FROM admission_ranks
               WHERE province='广东' AND exam_category='艺体类' AND group_code!=''
                 AND min_rank>0 AND year<2026 AND batch=?""",
            (BATCH,),
        ).fetchall()
    )
    det = set(
        tuple(r)
        for r in conn.execute(
            """SELECT DISTINCT college_id, group_code FROM admission_ranks
               WHERE province='广东' AND exam_category='艺体类' AND group_code!=''
                 AND major_id!='GEN' AND year<=2026 AND batch=?""",
            (BATCH,),
        ).fetchall()
    )
    missing = sorted(pool - det)

    # 2025 GEN 元数据
    g25_meta: dict[tuple[str, str], dict] = {}
    for r in conn.execute(
        """SELECT college_id, group_code, art_category, enrollment_count, min_rank, min_score
           FROM admission_ranks WHERE province='广东' AND exam_category='艺体类'
             AND year=2025 AND major_id='GEN' AND min_rank>0 AND batch=?""",
        (BATCH,),
    ).fetchall():
        g25_meta[(r["college_id"], r["group_code"])] = dict(r)

    # 2026 有专业明细的组（含类别 + 计划数合计）
    det_meta: dict[tuple[str, str], tuple[str, int]] = {}
    for r in conn.execute(
        """SELECT college_id, group_code, art_category, SUM(enrollment_count) AS plan
           FROM admission_ranks WHERE province='广东' AND exam_category='艺体类'
             AND year<=2026 AND major_id!='GEN' AND batch=?
           GROUP BY college_id, group_code""",
        (BATCH,),
    ).fetchall():
        det_meta[(r["college_id"], r["group_code"])] = (r["art_category"] or "", int(r["plan"] or 0))

    # 2025 已有位次的组号（冲突检测：目标组若 2025 已有 GEN，则跳过）
    g25_codes: set[tuple[str, str]] = set()
    for r in conn.execute(
        """SELECT DISTINCT college_id, group_code FROM admission_ranks
           WHERE province='广东' AND exam_category='艺体类' AND year=2025 AND major_id='GEN' AND batch=?""",
        (BATCH,),
    ).fetchall():
        g25_codes.add((r["college_id"], r["group_code"]))

    mapped: list[dict] = []
    skipped_conflict = 0
    skipped_nosource = 0
    skipped_ambig = 0
    skipped_lowconf = 0
    kept_same = 0

    for cid, g25 in missing:
        meta = g25_meta.get((cid, g25))
        if not meta:
            skipped_nosource += 1
            continue
        cat = meta["art_category"] or ""
        plan25 = int(meta["enrollment_count"] or 0)
        rank25 = int(meta["min_rank"] or 0)
        # 候选：同校同类别 2026 专业组
        cand = [
            (g26, pl) for (c2, g26), (c26, pl) in det_meta.items()
            if c2 == cid and c26 == cat
        ]
        if not cand:
            skipped_nosource += 1
            continue
        # 计划数最近者
        best = min(cand, key=lambda x: abs(x[1] - plan25))
        d = abs(best[1] - plan25)
        if len(cand) == 1:
            # 唯一候选：同校同类别仅 1 个 2026 组，不会错配 → 直接接受（计划数年际波动正常）
            g26 = best[0]
        else:
            # 多候选：需 Δplan 小且最佳/次佳可区分
            if plan25 > 0 and d > max(3, int(plan25 * 0.3)):
                skipped_lowconf += 1
                continue
            if plan25 == 0:
                skipped_ambig += 1
                continue
            cand2 = sorted(cand, key=lambda x: abs(x[1] - plan25))
            if abs(abs(cand2[0][1] - plan25) - abs(cand2[1][1] - plan25)) <= 1 and cand2[0][0] != cand2[1][0]:
                skipped_ambig += 1
                continue
            g26 = best[0]
        if (cid, g26) in g25_codes:
            skipped_conflict += 1
            continue
        mapped.append({
            "college_id": cid, "group_code_25": g25, "group_code_26": g26,
            "art_category": cat, "plan": plan25, "rank": rank25,
            "min_score": meta["min_score"],
        })

    print(f"缺组总数: {len(missing)}")
    print(f"  可映射: {len(mapped)} | 跳过冲突(2025目标组有位次): {skipped_conflict} | "
          f"无源: {skipped_nosource} | 歧义: {skipped_ambig} | 置信不足: {skipped_lowconf}")

    if not args.dry_run:
        for m in mapped:
            conn.execute(
                """INSERT OR IGNORE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score,
                    enrollment_count, exam_category, group_code, rank_source, art_category)
                   VALUES (?, 'GEN', '广东', 2025, ?, ?, ?, ?, '艺体类', ?, 'mapped', ?)""",
                (m["college_id"], BATCH, m["rank"], m["min_score"] or 0.0, m["plan"],
                 m["group_code_26"], m["art_category"]),
            )
            conn.execute(
                """DELETE FROM admission_ranks
                   WHERE province='广东' AND exam_category='艺体类' AND year=2025
                     AND major_id='GEN' AND batch=? AND college_id=? AND group_code=?""",
                (BATCH, m["college_id"], m["group_code_25"]),
            )
        conn.commit()
        print(f"已写入 {len(mapped)} 组映射")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
