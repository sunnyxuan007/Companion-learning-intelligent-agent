"""导入 2026 广东本科批专业级明细（从专家版 Excel）。

背景：2026 官方投档表只含组级 GEN 位次，无组内专业明细（本科批 99.7% 组 GEN-only）。
专家版 Excel（广东2026高考志愿大数据专家版0626.xlsx）的本科批次专业行组号与官方投档表
一致（100% 匹配），且含 学制/学费/计划数。本脚本把这些专业行写入 admission_ranks
（min_rank=0，位次靠组级 GEN 兜底）+ college_major_name 元数据。

用法：python scripts/import_batch_majors_2026.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
EXCEL = Path.home() / "桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"
DB = ROOT / "data/user/custom/deeptutor_custom.db"

EXCEL_BATCH = "本科批次"   # Excel 批次值
DB_BATCH = "本科批"        # DB 批次值
YEAR = 2026


def _safe_float(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(v):
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # 地方码 → 官方码
    code_map = {
        r["province_code"]: r["official_code"]
        for r in conn.execute(
            "SELECT province_code, official_code FROM college_code_map WHERE province='广东'"
        ).fetchall()
    }

    # DB 现有 2026 本科批 GEN 组（官方码, 组号）
    db_gen = set()
    for r in conn.execute(
        "SELECT college_id, group_code FROM admission_ranks WHERE province='广东' AND year=? AND batch=? AND major_id='GEN'",
        (YEAR, DB_BATCH),
    ).fetchall():
        db_gen.add((r["college_id"], r["group_code"]))

    # 读取 Excel 本科批次专业行（col: 0年份,3批次,4校码,5校名,7组号,8组名,9专业码,10全称,11名称,16计划,17学制,18学费,15选科）
    wb = openpyxl.load_workbook(EXCEL, read_only=True)
    ws = wb.active
    rows = []
    total = 0
    skipped_no_gen = 0
    skipped_batch = 0
    unmatched_college = 0
    for row in ws.iter_rows(min_row=4, values_only=True):
        if str(row[3] or "").strip() != EXCEL_BATCH:
            continue
        cat = str(row[2] or "").strip()
        if cat not in ("物理", "历史"):
            continue
        local = str(row[4] or "").strip()
        if not local or not row[5]:
            continue
        off = code_map.get(local)
        gc = str(row[7] or "").strip()
        mid = str(row[9] or "").strip()
        if not off or not gc or not mid:
            continue
        gkey = (off, gc)
        # 只补 DB 已有 GEN 组的专业明细
        if gkey not in db_gen:
            skipped_no_gen += 1
            continue
        rows.append({
            "college_id": off,
            "group_code": gc,
            "major_id": mid,
            "exam_category": cat,
            "major_name": str(row[11] or "").strip() or str(row[10] or "").strip(),
            "full_name": str(row[10] or "").strip(),
            "subject_requirement": str(row[15] or "").strip(),
            "plan": _safe_int(row[16]),
            "years": _safe_int(row[17]),
            "tuition": _safe_float(row[18]),
        })
        total += 1
    wb.close()

    print(f"Excel 本科批次专业行: {total}（组级 GEN 匹配通过）")
    print(f"  跳过无 GEN 组: {skipped_no_gen}，跳过批次: {skipped_batch}，未匹配院校: {unmatched_college}")

    if args.dry_run:
        print(f"[dry-run] 不写入。将插入 {total} 专业行 + {total} college_major_name 行")
        conn.close()
        return 0

    # 去重（同校同组同专业可能多行——不同选科？只保留第一条）
    seen = set()
    dedup = []
    for r in rows:
        k = (r["college_id"], r["group_code"], r["major_id"], r["exam_category"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)

    n_rank = 0
    n_name = 0
    for r in dedup:
        conn.execute(
            """INSERT OR REPLACE INTO admission_ranks
               (college_id, major_id, province, year, batch, min_rank, min_score,
                enrollment_count, exam_category, group_code)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r["college_id"], r["major_id"], "广东", YEAR, DB_BATCH, 0, 0.0,
             r["plan"], r["exam_category"], r["group_code"]),
        )
        n_rank += 1
        conn.execute(
            """INSERT OR REPLACE INTO college_major_name
               (college_id, major_id, major_name, full_name, category, subject_requirement,
                tuition, years, campus)
               VALUES (?,?,?,?,?,?,?,?,'')""",
            (r["college_id"], r["major_id"], r["major_name"], r["full_name"], "",
             r["subject_requirement"], r["tuition"], r["years"]),
        )
        n_name += 1

    conn.commit()
    print(f"已写入: admission_ranks {n_rank} 专业行（去重后）, college_major_name {n_name} 行")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())