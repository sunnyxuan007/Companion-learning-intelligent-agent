"""重建院校-专业名映射表 college_major_name。

数据源：广东2026高考志愿大数据专家版0626.xlsx（专业级明细）。
说明：库里 admission_ranks.major_id 是"院校内专业序号"，majors 表却是全局 ID，
导致专业名全部错位（如哈理工 008 实际是金属材料工程，majors.008=保险学）。
本脚本用 Excel 的院校内专业名重建映射，推荐引擎改为从该表取专业名。

用法：python scripts/backfill_major_names.py [--excel 路径] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from deeptutor.services.custom.db import get_connection

DEFAULT_EXCEL = "/home/sunnyxuan2/桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"


def build_local_to_official(conn) -> dict[str, str]:
    """college_code_map: province_code -> official_code（广东，gd_local 优先）"""
    rows = conn.execute(
        "SELECT official_code, province_code, source FROM college_code_map WHERE province='广东'"
    ).fetchall()
    mapping: dict[str, str] = {}
    priority = {"gd_local": 0, "gd_variant": 1, "gd_gaokao2026": 2, "official_rename": 3}
    for r in rows:
        pc = r["province_code"]
        oc = r["official_code"]
        src = r["source"] or ""
        # 多码映射到同一官方码时，gd_local 优先
        if pc not in mapping or priority.get(src, 9) < priority.get(mapping.get(pc, ""), 9):
            mapping[pc] = oc
    return mapping


def load_excel_major_names(excel_path: str) -> dict[str, dict[str, dict]]:
    """返回 {official_code: {major_id: {major_name, full_name, category, subject_requirement, tuition}}}"""
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    ws = wb.active

    # 先预读 college_code_map 以外的变体：Excel 校名含 (高校专项) 等，code 与普通相同
    raw: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in ws.iter_rows(min_row=4, values_only=True):
        cid = str(row[4] or "").strip()
        major_id = str(row[9] or "").strip()
        if not cid or not major_id or major_id == "GEN":
            continue
        major_name = str(row[11] or "").strip() or str(row[10] or "").strip()
        if not major_name:
            continue
        full_name = str(row[10] or "").strip()
        category = str(row[22] or "").strip()
        subject_req = str(row[15] or "").strip()
        try:
            tuition = float(row[18] or 0)
        except (TypeError, ValueError):
            tuition = 0
        rec = raw[cid].setdefault(major_id, {
            "major_name": major_name,
            "full_name": full_name,
            "category": category,
            "subject_requirement": subject_req,
            "tuition": tuition,
        })
        # 优先保留更完整的专业名（取备注更长的）
        if len(major_name) > len(rec["major_name"]):
            rec["major_name"] = major_name
        if len(full_name) > len(rec["full_name"]):
            rec["full_name"] = full_name
        if not rec["category"] and category:
            rec["category"] = category
    wb.close()
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", default=DEFAULT_EXCEL)
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = parser.parse_args()

    conn = get_connection()
    local_map = build_local_to_official(conn)
    raw = load_excel_major_names(args.excel)

    # 转换：Excel 广东码 -> 官方码
    resolved: dict[str, dict[str, dict]] = defaultdict(dict)
    unmapped_codes: set[str] = set()
    for cid, majors in raw.items():
        official = local_map.get(cid)
        if not official:
            # 变体/未在映射表的（如预科班 V2013f2）
            unmapped_codes.add(cid)
            continue
        for mid, rec in majors.items():
            resolved[official].setdefault(mid, rec)

    total_pairs = sum(len(v) for v in resolved.values())

    print(f"Excel 专业对: {sum(len(v) for v in raw.values())}")
    print(f"转换官方码后: {total_pairs} 对 / {len(resolved)} 校")
    print(f"未映射广东码: {len(unmapped_codes)} 个（{sorted(unmapped_codes)[:10]}...）")

    if args.dry_run:
        conn.close()
        return 0

    # 写入 college_major_name（INSERT OR REPLACE）
    n = 0
    for college_id, majors in resolved.items():
        for mid, rec in majors.items():
            conn.execute(
                """INSERT OR REPLACE INTO college_major_name
                   (college_id, major_id, major_name, full_name, category, subject_requirement, tuition)
                   VALUES (?,?,?,?,?,?,?)""",
                (college_id, mid, rec["major_name"], rec["full_name"],
                 rec["category"], rec["subject_requirement"], rec["tuition"]),
            )
            n += 1
    conn.commit()
    print(f"已写入 college_major_name: {n} 行")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())