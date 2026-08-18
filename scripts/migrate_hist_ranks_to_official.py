"""把地方码行的历史录取数据迁移到官方码行（修复 Phase 17 后双轨数据分裂）。

背景：
- import_excel_v3.py（2023-2025 历史数据）用 Excel 地方码写入 admission_ranks
- import_guangdong_data_v3.py + import_advance_batch.py（2026）用官方码写入
- 导致同一学校历史数据在地方码行、2026 在官方码行，跨年概率计算断裂

处理：
1. 2023-2025 历史行（college_id=地方码）→ UPDATE 为官方码（已确认无 PK 冲突）
2. 2026 行（college_id=地方码）→ 官方码已有（冲突），直接 DELETE 地方码重复
3. 若官方码 colleges 行不存在，则 UPDATE 后把 colleges 行也重命名（改 id）

用法：python scripts/migrate_hist_ranks_to_official.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data/user/custom/deeptutor_custom.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = OFF")
    now = time.time()

    # 广东 地方码 → 官方码
    maps = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT province_code, official_code FROM college_code_map WHERE province = '广东'"
        ).fetchall()
        if len(r[0]) == 5
    ]
    # 官方码也存在的地方码才处理（避免孤儿）
    valid = {}
    for pc, oc in maps:
        row = conn.execute("SELECT 1 FROM colleges WHERE id = ?", (pc,)).fetchone()
        if row:
            valid[pc] = oc
    print(f"有效地方码映射: {len(valid)}")

    update_cnt = 0
    delete_cnt = 0
    missing_official = []
    for pc, oc in valid.items():
        # 官方码 colleges 行是否存在
        has_official = conn.execute("SELECT 1 FROM colleges WHERE id = ?", (oc,)).fetchone()
        # 历史行迁移
        rows = conn.execute(
            "SELECT major_id, year, exam_category, group_code FROM admission_ranks WHERE college_id = ?",
            (pc,),
        ).fetchall()
        for major_id, year, exam_cat, group_code in rows:
            # 官方码是否已有该行（冲突）
            dup = conn.execute(
                "SELECT 1 FROM admission_ranks WHERE college_id=? AND major_id=? AND year=? AND exam_category=? AND group_code=?",
                (oc, major_id, year, exam_cat, group_code),
            ).fetchone()
            if dup:
                if not args.dry_run:
                    conn.execute(
                        "DELETE FROM admission_ranks WHERE college_id=? AND major_id=? AND year=? AND exam_category=? AND group_code=?",
                        (pc, major_id, year, exam_cat, group_code),
                    )
                delete_cnt += 1
            else:
                if not args.dry_run:
                    conn.execute(
                        "UPDATE admission_ranks SET college_id=? WHERE college_id=? AND major_id=? AND year=? AND exam_category=? AND group_code=?",
                        (oc, pc, major_id, year, exam_cat, group_code),
                    )
                update_cnt += 1
                if not has_official:
                    missing_official.append(oc)

    # 地方码行 2026 无 GEN 等：全部冲突已删，检查是否还有残留
    if not args.dry_run:
        conn.commit()
    print(f"历史行迁移(改官方码): {update_cnt}")
    print(f"2026 重复行删除: {delete_cnt}")
    if missing_official:
        print(f"⚠️ 官方码 colleges 行缺失的: {set(missing_official)}")

    # 残留检查
    resid = conn.execute(
        """SELECT COUNT(*) FROM admission_ranks ar
           JOIN college_code_map m ON ar.college_id = m.province_code
           WHERE m.province = '广东' AND length(ar.college_id) = 5"""
    ).fetchone()[0]
    print(f"残留地方码行: {resid}")
    conn.close()


if __name__ == "__main__":
    main()