"""Re-import Guangdong data with 专业组 (group_code) preserved.

Imports:
  1. 一分一段 (score_rank_segments): 物理+历史 2025
  2. 投档数据 (admission_ranks): 物理2025 + 历史2026, with exam_category + group_code
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from deeptutor.services.custom.admission_dao import (
    bulk_import_ranks,
    bulk_import_score_rank,
)
from deeptutor.services.custom.db import get_connection, init_db

FILE_HISTORY_RANK = Path(
    "/home/sunnyxuan2/桌面/data for agent/1.广东省2025年高考普通类（历史）分数段统计表（含本、专科层次加分）.xlsx"
)
FILE_PHYSICS_RANK = Path(
    "/home/sunnyxuan2/桌面/data for agent/2.广东省2025年高考普通类（物理）分数段统计表（含本、专科层次加分）.xlsx"
)
FILE_HISTORY_ADMISSION = Path(
    "/home/sunnyxuan2/桌面/data for agent/附件1 广东省2026年本科普通类(历史)投档情况.xlsx"
)
FILE_PHYSICS_ADMISSION = Path(
    "/home/sunnyxuan2/桌面/data for agent/附件2 广东省2026年本科普通类(物理)投档情况.xlsx"
)

PROVINCE = "广东"


def _parse_score_rank(filepath: Path, exam_category: str) -> list[dict]:
    """Parse 一分一段 Excel (both 本科 and 专科)."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(min_row=4, values_only=True))
    wb.close()

    records: list[dict] = []
    for score, undergrad_count, undergrad_cum, voc_count, voc_cum in rows:
        if score is None:
            continue
        try:
            s = int(float(str(score).strip()))
        except (ValueError, TypeError):
            continue

        if undergrad_cum is not None:
            try:
                records.append({
                    "province": PROVINCE,
                    "year": 2025,
                    "exam_category": exam_category,
                    "score": s,
                    "cumulative_rank": int(float(str(undergrad_cum).strip())),
                    "batch_category": "本科",
                })
            except (ValueError, TypeError):
                pass

        if voc_cum is not None:
            try:
                records.append({
                    "province": PROVINCE,
                    "year": 2025,
                    "exam_category": exam_category,
                    "score": s,
                    "cumulative_rank": int(float(str(voc_cum).strip())),
                    "batch_category": "专科",
                })
            except (ValueError, TypeError):
                pass

    return records


def _parse_admission(filepath: Path, exam_category: str, year: int) -> list[dict]:
    """Parse 投档 Excel, preserving group_code per row."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    wb.close()

    from deeptutor.services.custom.db import get_connection
    conn = get_connection()
    name_to_id = {}
    for r in conn.execute("SELECT id, name FROM colleges").fetchall():
        name_to_id[r["name"]] = r["id"]
    code_map = {}
    for r in conn.execute(
        "SELECT province_code, official_code FROM college_code_map WHERE province = ?",
        (PROVINCE,),
    ).fetchall():
        code_map[str(r[0]).strip()] = str(r[1])
    conn.close()

    records: list[dict] = []
    errors = 0
    for row in rows:
        if not row or row[0] is None:
            continue
        try:
            college_code = str(int(float(str(row[0]).strip())))
            college_name = str(row[1]).strip() if row[1] else ""
            group_code = str(int(float(str(row[2]).strip()))) if row[2] else ""
            plan_count = int(float(str(row[3]).strip())) if row[3] else 0
            admitted = int(float(str(row[4]).strip())) if row[4] else 0
            min_score = float(str(row[5]).strip()) if row[5] else 0
            min_rank = int(float(str(row[6]).strip())) if row[6] else 0
        except (ValueError, TypeError, IndexError):
            errors += 1
            continue

        # 优先代码映射（官方表地方码 → 官方码），fallback 名称匹配（strip 尾空格）
        college_id = code_map.get(college_code)
        if not college_id:
            college_id = name_to_id.get(college_name)
        if not college_id and "(" in college_name:
            base_name = college_name.split("(")[0].strip()
            college_id = name_to_id.get(base_name)

        if not college_id:
            errors += 1
            continue

        records.append({
            "college_id": college_id,
            "major_id": "GEN",
            "province": PROVINCE,
            "year": year,
            "batch": "本科批",
            "min_rank": min_rank,
            "min_score": min_score,
            "enrollment_count": plan_count,
            "exam_category": exam_category,
            "group_code": group_code,
        })

    return records, errors


def run():
    init_db()

    # Clear old Guangdong data
    conn = get_connection()
    old_rank = conn.execute(
        "SELECT COUNT(*) FROM admission_ranks WHERE province = ?", (PROVINCE,)
    ).fetchone()[0]
    conn.execute("DELETE FROM admission_ranks WHERE province = ?", (PROVINCE,))
    conn.execute("DELETE FROM score_rank_segments WHERE province = ?", (PROVINCE,))
    conn.commit()
    conn.close()
    print(f"Cleared {old_rank} old admission_ranks + old score_rank_segments for 广东")

    # --- 1. Import 一分一段 ---
    print("\n=== Importing 一分一段 (score_rank_segments) ===")
    for label, fpath, exam_cat in [
        ("物理", FILE_PHYSICS_RANK, "物理"),
        ("历史", FILE_HISTORY_RANK, "历史"),
    ]:
        recs = _parse_score_rank(fpath, exam_cat)
        n = bulk_import_score_rank(recs)
        print(f"  {label}: {n} records imported")

    # --- 2. Import 投档数据 with group_code ---
    print("\n=== Importing 投档数据 (admission_ranks, with group_code) ===")
    total_ok = 0
    total_err = 0
    for label, fpath, exam_cat, year in [
        ("物理 2026", FILE_PHYSICS_ADMISSION, "物理", 2026),
        ("历史 2026", FILE_HISTORY_ADMISSION, "历史", 2026),
    ]:
        recs, errs = _parse_admission(fpath, exam_cat, year)
        n = bulk_import_ranks(recs)
        total_ok += n
        total_err += errs
        print(f"  {label}: {n} ok, {errs} errors")

    print(f"\nDone: {total_ok} admission records, {total_err} unmapped schools")

    # Verify
    conn = get_connection()
    for cat in ("物理", "历史"):
        cnt = conn.execute(
            "SELECT COUNT(*) FROM admission_ranks WHERE province = ? AND exam_category = ?",
            (PROVINCE, cat),
        ).fetchone()[0]
        groups = conn.execute(
            "SELECT COUNT(DISTINCT group_code) FROM admission_ranks WHERE province = ? AND exam_category = ? AND group_code != ''",
            (PROVINCE, cat),
        ).fetchone()[0]
        total_cand = conn.execute(
            "SELECT cumulative_rank FROM score_rank_segments WHERE province = ? AND exam_category = ? AND batch_category = '本科' ORDER BY score ASC LIMIT 1",
            (PROVINCE, cat),
        ).fetchone()
        tc = total_cand[0] if total_cand else 0
        print(f"  {cat}: {cnt} admission records, {groups} distinct groups, {tc} total candidates")
    conn.close()


if __name__ == "__main__":
    run()
