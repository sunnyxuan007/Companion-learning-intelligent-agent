"""为 college_major_name 回填 学制(years) / 校区(campus) 字段。

数据源：广东2026高考志愿大数据专家版0626.xlsx
- 学制: 第18列（col17, 0-based row[17]），如 4 / 5 / 3
- 校区: 专业备注（col12, row[12]）正则提取，如 (仙溪校区) / (校本部) / (龙湖东校区)
- 学费: 已有 tuition 列，本脚本顺带核对不回写

用法：python scripts/backfill_major_meta.py [--excel 路径] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from deeptutor.services.custom.db import get_connection

DEFAULT_EXCEL = "/home/sunnyxuan2/桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"

CAMPUS_RE = re.compile(r"[（(]([^（()）]{0,12}?(?:校区|校本部|龙洞|大学城|石牌))[）)]")


def extract_campus(note: str) -> str:
    m = CAMPUS_RE.search(note or "")
    return m.group(1).strip() if m else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", default=DEFAULT_EXCEL)
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = parser.parse_args()

    conn = get_connection()
    # college_code_map: province_code -> official_code（广东，gd_local 优先）
    rows = conn.execute(
        "SELECT official_code, province_code, source FROM college_code_map WHERE province='广东'"
    ).fetchall()
    mapping: dict[str, str] = {}
    priority = {"gd_local": 0, "gd_variant": 1, "gd_gaokao2026": 2, "official_rename": 3}
    for oc, pc, src in rows:
        if pc not in mapping or priority.get(src or "", 9) < priority.get(mapping.get(pc, ""), 9):
            mapping[pc] = oc

    wb = openpyxl.load_workbook(args.excel, read_only=True)
    ws = wb.active

    updates: dict[tuple[str, str], tuple[str, str]] = {}
    stats = {"years": 0, "campus": 0}
    for row in ws.iter_rows(min_row=4, values_only=True):
        cid = str(row[4] or "").strip()
        major_id = str(row[9] or "").strip()
        if not cid or not major_id or major_id == "GEN":
            continue
        official = mapping.get(cid)
        if not official:
            continue
        years = str(row[17] or "").strip()
        campus = extract_campus(str(row[12] or ""))
        key = (official, major_id)
        cur_years, cur_campus = updates.get(key, ("", ""))
        if years and not cur_years:
            cur_years = years
        if campus and not cur_campus:
            cur_campus = campus
        updates[key] = (cur_years, cur_campus)
    wb.close()

    stats["years"] = sum(1 for y, _ in updates.values() if y)
    stats["campus"] = sum(1 for _, c in updates.values() if c)
    print(f"待更新专业对: {len(updates)}（含学制 {stats['years']}，校区 {stats['campus']}）")
    if args.dry_run:
        conn.close()
        return 0

    n = 0
    for (college_id, major_id), (years, campus) in updates.items():
        cur = conn.execute(
            "SELECT years, campus FROM college_major_name WHERE college_id=? AND major_id=?",
            (college_id, major_id),
        ).fetchone()
        if not cur:
            continue
        new_years = years or cur[0] or ""
        new_campus = campus or cur[1] or ""
        if new_years != cur[0] or new_campus != cur[1]:
            conn.execute(
                "UPDATE college_major_name SET years=?, campus=? WHERE college_id=? AND major_id=?",
                (new_years, new_campus, college_id, major_id),
            )
            n += 1
    conn.commit()
    print(f"已更新 college_major_name: {n} 行")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())