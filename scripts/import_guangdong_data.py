"""Import Guangdong province admission rank data from multiple Excel files.

Usage:
    python scripts/import_guangdong_data.py
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import openpyxl

from deeptutor.services.custom.admission_dao import bulk_import_ranks
from deeptutor.services.custom.db import get_connection, init_db

DATA_DIR = Path("/home/sunnyxuan2/桌面/data for agent")

# Files to process
FILES = [
    ("附件1 广东省2026年本科普通类(历史)投档情况.xlsx", "simple", 2026, "历史"),
    ("附件2 广东省2025年本科普通类（物理）投档情况.xlsx", "simple", 2025, "物理"),
    ("广东-2026-专家版数据（23-26）(5).xlsx", "expert", None, None),
]


def _strip_name(name: str) -> str:
    return re.sub(r"\s+", "", name).strip()


def _build_college_mapping() -> dict[str, str]:
    """Build a mapping from college name → our CU ID."""
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM colleges").fetchall()
    conn.close()

    exact: dict[str, str] = {}
    for r in rows:
        exact[_strip_name(r["name"])] = r["id"]

    # Common name normalization rules
    NORMALIZE_RULES: dict[str, str] = {
        "清华大学": "清华大学",
        "北京大学": "北京大学",
    }

    def _fuzzy_find(name: str) -> str | None:
        cleaned = _strip_name(name)
        if cleaned in exact:
            return exact[cleaned]

        # Try removing parenthetical suffixes like (苏州校区), (北京), etc.
        base = re.sub(r"[（(][^）)]*[）)]", "", cleaned).strip()
        if base in exact:
            return exact[base]

        # Try matching by substring (at least 4 chars)
        for db_name, db_id in exact.items():
            if len(cleaned) >= 4 and (cleaned in db_name or db_name in cleaned):
                return db_id

        return None

    # We'll build it lazily, but return a closure
    return exact


def _normalize_college_name(name: str) -> str:
    """Normalize known naming differences."""
    n = _strip_name(name)
    n = re.sub(r"[（(]高校专项计划[）)]", "", n)
    n = re.sub(r"[（(]中外合作办学[）)]", "", n)
    n = re.sub(r"[（(]协同培养[）)]", "", n)
    n = re.sub(r"\s*\(.*?\)\s*", "", n)
    n = re.sub(r"\s*[（(].*?[）)]\s*", "", n)
    return _strip_name(n)


def import_simple_file(path: Path, year: int, track: str, name_map: dict[str, str]):
    """Import a simple attachment file (program group level data)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    wb.close()

    records: list[dict[str, Any]] = []
    matched = skipped_no_match = skipped_no_id = 0
    # First pass: collect all college names to match
    to_match: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if r[0] and r[1]:
            name = _strip_name(str(r[1]))
            if name not in to_match:
                to_match[name] = []
            to_match[name].append(i)

    # Try matching from our name map
    college_code_map: dict[str, str] = {}
    for name in to_match:
        n = _normalize_college_name(name)
        cu_id = name_map.get(n)
        if cu_id:
            college_code_map[name] = cu_id
        else:
            # Try fuzzy
            base = re.sub(r"[（(][^）)]*[）)]", "", n).strip()
            cu_id = name_map.get(base)
            if cu_id:
                college_code_map[name] = cu_id

    # Build reverse mapping from official code → our ID (if we can get it)
    code_map: dict[str, str] = {}
    for r in rows:
        if r[0] and r[1]:
            code = str(int(r[0]))
            name = _strip_name(str(r[1]))
            cu_id = college_code_map.get(name)
            if cu_id and code not in code_map:
                code_map[str(int(r[0]))] = cu_id

    print(f"  Matched {len(code_map)}/{len(to_match)} unique colleges")

    for r in rows:
        if not r[0] or not r[1]:
            skipped_no_id += 1
            continue
        code = str(int(r[0]))
        name = _strip_name(str(r[1]))

        college_id = code_map.get(code)
        if not college_id:
            skipped_no_match += 1
            continue

        def _safe_int(v, default=0):
            if v is None or str(v).strip() in ("", "-", "--", "\\"):
                return default
            try:
                return int(float(str(v).strip()))
            except (ValueError, TypeError):
                return default

        def _safe_float(v, default=0.0):
            if v is None or str(v).strip() in ("", "-", "--", "\\"):
                return default
            try:
                return float(str(v).strip())
            except (ValueError, TypeError):
                return default

        records.append({
            "college_id": college_id,
            "major_id": "GEN",
            "province": "广东",
            "year": year,
            "batch": "本科批",
            "min_rank": _safe_int(r[6]),
            "min_score": _safe_float(r[5]),
            "enrollment_count": _safe_int(r[3]),
        })

    if records:
        count = bulk_import_ranks(records)
        print(f"  Imported {count}/{len(records)} records "
              f"(skipped: {skipped_no_match} unmatched, {skipped_no_id} no ID)")
    else:
        print(f"  No records to import (skipped: {skipped_no_match} unmatched)")


def import_expert_file(path: Path, name_map: dict[str, str]):
    """Import the comprehensive expert data file with multi-year data."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    wb.close()

    print(f"  Parsing {len(rows)} rows...")

    # Build college code → CU ID mapping
    code_map: dict[str, str] = {}
    for r in rows:
        code = str(int(r[5])) if r[5] and str(r[5]).isdigit() else ""
        name = _strip_name(str(r[6])) if r[6] else ""
        if code and name and code not in code_map:
            n = _normalize_college_name(name)
            cu_id = name_map.get(n)
            if not cu_id:
                base = re.sub(r"[（(][^）)]*[）)]", "", n).strip()
                cu_id = name_map.get(base)
            if cu_id:
                code_map[code] = cu_id

    print(f"  Matched {len(code_map)} unique colleges")

    # Column layout (0-indexed):
    # [28]专业组录取人数1, [29]专业组最低分1, [30]专业组最低位次1 — 2025 group
    # [31]录取人数1, [32]最低分1, [33]最低位次1, [34]老批次1 — 2025 individual
    # [36]录取人数2, [37]最低分2, [38]最低位次2             — 2024 individual
    # [41]录取人数3, [42]最低分3, [43]最低位次3             — 2023 individual
    YEAR_COLS: dict[int, tuple[int, int, int]] = {
        2025: (29, 30, 28),  # score=29, rank=30, enroll=28 (专业组 level)
        2024: (37, 38, 36),  # score=37, rank=38, enroll=36
        2023: (42, 43, 41),  # score=42, rank=43, enroll=41
    }

    def _safe_int(v, default=0):
        if v is None or str(v).strip() in ("", "-", "--", "\\", "None"):
            return default
        try:
            return int(float(str(v).strip()))
        except (ValueError, TypeError):
            return default

    def _safe_float(v, default=0.0):
        if v is None or str(v).strip() in ("", "-", "--", "\\", "None"):
            return default
        try:
            return float(str(v).strip())
        except (ValueError, TypeError):
            return default

    records: list[dict[str, Any]] = []
    unmatched = 0

    for r in rows:
        code = str(int(r[5])) if r[5] and str(r[5]).isdigit() else ""
        college_id = code_map.get(code, "")
        if not college_id:
            unmatched += 1
            continue

        province = _strip_name(str(r[2])) if r[2] else "广东"
        batch = _strip_name(str(r[4])) if r[4] else "本科批"
        major_id = _strip_name(str(r[10])) if r[10] else ""
        plan_count = _safe_int(r[17])

        # Extract data for each year from the respective columns
        for year, (score_col, rank_col, enroll_col) in YEAR_COLS.items():
            min_score = _safe_float(r[score_col])
            min_rank = _safe_int(r[rank_col])
            enroll = _safe_int(r[enroll_col])

            if min_rank > 0 or min_score > 0:
                records.append({
                    "college_id": college_id,
                    "major_id": "GEN",
                    "province": province,
                    "year": year,
                    "batch": batch,
                    "min_rank": min_rank,
                    "min_score": min_score,
                    "enrollment_count": max(enroll, plan_count),
                })

    print(f"  Extracted {len(records)} admission records, {unmatched} skipped (unmatched college)")

    if records:
        count = bulk_import_ranks(records)
        print(f"  Imported {count} records into admission_ranks")
    else:
        print("  No records to import")


def run():
    init_db()
    t0 = time.time()

    # Build college name map from our database
    print("Building college name mapping...")
    conn = get_connection()
    db_rows = conn.execute("SELECT id, name FROM colleges").fetchall()
    conn.close()
    name_map: dict[str, str] = {}
    for r in db_rows:
        name_map[_strip_name(r["name"])] = r["id"]
    print(f"  {len(name_map)} colleges in database")

    for filename, filetype, year, track in FILES:
        path = DATA_DIR / filename
        if not path.exists():
            print(f"\n[SKIP] {filename}: not found")
            continue

        print(f"\n=== {filename} ===")
        if filetype == "simple":
            import_simple_file(path, year, track, name_map)
        elif filetype == "expert":
            import_expert_file(path, name_map)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    # Verify final count
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM admission_ranks").fetchone()[0]
    conn.close()
    print(f"Total admission_ranks records: {count}")


if __name__ == "__main__":
    run()
