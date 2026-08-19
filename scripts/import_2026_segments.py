"""Import 广东省 2026 一分一段（分数段统计表）Excel -> score_rank_segments.

- 表头 5 行（标题 + 列名），数据从第 6 行起
- 列：文化总分 / 本科人数 / 本科累计 / 专科人数 / 专科累计
- 首行分数形如 "669（含以上）"，剥离括号保留该行（v2 用 int() 会丢首行）
- 仅写入 year=2026，不动 2025 行（INSERT OR REPLACE 按主键只覆盖同 year 行）
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from deeptutor.services.custom.admission_dao import bulk_import_score_rank
from deeptutor.services.custom.db import get_connection, init_db

PROVINCE = "广东"
YEAR = 2026

FILE_HISTORY = Path(
    "/home/sunnyxuan2/桌面/data for agent/1.广东省2026年高考普通类（历史）分数段统计表（含本、专科层次加分）.xlsx"
)
FILE_PHYSICS = Path(
    "/home/sunnyxuan2/桌面/data for agent/2.广东省2026年高考普通类（物理）分数段统计表（含本、专科层次加分）.xlsx"
)


def _strip_above(value: object) -> int:
    """'669（含以上）' -> 669；'668' -> 668。"""
    s = str(value).strip()
    for mark in ("（含以上）", "(含以上)", "含以上"):
        if mark in s:
            s = s.split(mark)[0]
            break
    return int(float(s))


def _parse(filepath: Path, exam_category: str) -> list[dict]:
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(min_row=6, values_only=True))
    wb.close()

    records: list[dict] = []
    for row in rows:
        if not row or row[0] is None:
            continue
        try:
            s = _strip_above(row[0])
        except (ValueError, TypeError):
            continue

        # row: score, undergrad_count, undergrad_cum, voc_count, voc_cum
        if row[2] is not None:
            try:
                records.append({
                    "province": PROVINCE,
                    "year": YEAR,
                    "exam_category": exam_category,
                    "score": s,
                    "cumulative_rank": int(float(str(row[2]).strip())),
                    "batch_category": "本科",
                })
            except (ValueError, TypeError):
                pass
        if row[4] is not None:
            try:
                records.append({
                    "province": PROVINCE,
                    "year": YEAR,
                    "exam_category": exam_category,
                    "score": s,
                    "cumulative_rank": int(float(str(row[4]).strip())),
                    "batch_category": "专科",
                })
            except (ValueError, TypeError):
                pass

    return records


def main() -> None:
    init_db()
    for filepath, cat in [(FILE_HISTORY, "历史"), (FILE_PHYSICS, "物理")]:
        if not filepath.exists():
            print(f"SKIP: {filepath} 不存在")
            continue
        recs = _parse(filepath, cat)
        n = bulk_import_score_rank(recs)
        print(f"{cat}: {filepath.name} -> {n} 条 (year={YEAR})")

    conn = get_connection()
    for cat in ("历史", "物理"):
        rows = conn.execute(
            "SELECT batch_category, COUNT(*), MIN(score), MAX(score) FROM score_rank_segments "
            "WHERE province=? AND year=? AND exam_category=? GROUP BY batch_category",
            (PROVINCE, YEAR, cat),
        ).fetchall()
        for r in rows:
            print(f"  2026 {cat} {r[0]}: {r[1]} 行, 分数 {r[2]}~{r[3]}")
    conn.close()


if __name__ == "__main__":
    main()