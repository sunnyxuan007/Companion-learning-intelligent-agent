"""回填 college_major_name.medical_note：从 Excel 专家版「专业备注」列提取体检限制片段。

数据源：广东2026高考志愿大数据专家版0626.xlsx
  col4=院校代码(地方码), col9=专业代码, col12=专业备注, col5=院校名称
匹配：地方码 → college_code_map → 官方码；按 (college_id, major_id) UPDATE college_major_name。
幂等：重复运行仅覆盖相同值；medical_note 为空的行跳过。
用法：
  python scripts/backfill_medical_notes.py [--dry-run] [--excel PATH]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import openpyxl  # noqa: E402

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402
from deeptutor.services.custom.medical_dao import extract_medical_clause  # noqa: E402

DEFAULT_EXCEL = "/home/sunnyxuan2/桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--excel", default=DEFAULT_EXCEL)
    args = ap.parse_args()

    conn = sqlite3.connect(get_custom_db_path())
    conn.row_factory = sqlite3.Row
    code_map = {
        r["province_code"]: r["official_code"]
        for r in conn.execute(
            "SELECT province_code, official_code FROM college_code_map WHERE province='广东'"
        ).fetchall()
    }

    wb = openpyxl.load_workbook(args.excel, read_only=True)
    ws = wb.active
    updates: dict[tuple[str, str], str] = {}
    total_notes = 0
    batch_stats: dict[str, int] = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        local = str(row[4] or "").strip()
        mid = str(row[9] or "").strip()
        note_raw = str(row[12] or "").strip() if len(row) > 12 else ""
        if not local or not mid or not note_raw:
            continue
        clause = extract_medical_clause(note_raw)
        if not clause:
            continue
        off = code_map.get(local)
        if not off:
            continue
        batch = str(row[3] or "").strip()
        batch_stats[batch] = batch_stats.get(batch, 0) + 1
        updates[(off, mid)] = clause
        total_notes += 1
    wb.close()

    print(f"备注含体检限制行: {total_notes} | 批次分布: {batch_stats}")

    matched = 0
    unmatched = 0
    existing = 0
    for (off, mid), clause in updates.items():
        cur = conn.execute(
            "SELECT medical_note FROM college_major_name WHERE college_id=? AND major_id=?",
            (off, mid),
        ).fetchone()
        if cur is None:
            unmatched += 1
            continue
        if cur["medical_note"] == clause:
            existing += 1
            continue
        if not args.dry_run:
            conn.execute(
                "UPDATE college_major_name SET medical_note=? WHERE college_id=? AND major_id=?",
                (clause, off, mid),
            )
        matched += 1
    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"匹配更新: {matched} | 已相同跳过: {existing} | 未匹配到 college_major_name: {unmatched}")
    if args.dry_run:
        print("(--dry-run 未写入)")
    return 0


if __name__ == "__main__":
    sys.exit(main())