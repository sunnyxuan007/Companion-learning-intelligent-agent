from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any

import openpyxl

from deeptutor.services.custom.admission_dao import bulk_import_ranks
from deeptutor.services.custom.db import get_connection, init_db

COLUMN_ALIASES: dict[str, str] = {
    "college_id": "college_id",
    "院校id": "college_id",
    "院校": "college_id",
    "学校id": "college_id",
    "学校": "college_id",
    "major_id": "major_id",
    "专业id": "major_id",
    "专业": "major_id",
    "province": "province",
    "省份": "province",
    "省": "province",
    "year": "year",
    "年份": "year",
    "batch": "batch",
    "批次": "batch",
    "min_rank": "min_rank",
    "最低位次": "min_rank",
    "位次": "min_rank",
    "最低排名": "min_rank",
    "min_score": "min_score",
    "最低分数": "min_score",
    "最低分": "min_score",
    "分数": "min_score",
    "enrollment_count": "enrollment_count",
    "招生人数": "enrollment_count",
    "人数": "enrollment_count",
    "计划数": "enrollment_count",
}

REQUIRED_KEYS = ["college_id", "major_id", "province", "year"]
OPTIONAL_KEYS = ["batch", "min_rank", "min_score", "enrollment_count"]


def _resolve_columns(headers: list[str]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    unknown: list[str] = []
    for i, h in enumerate(headers):
        h_clean = h.strip().lower()
        resolved = COLUMN_ALIASES.get(h_clean)
        if resolved:
            mapping[i] = resolved
        else:
            unknown.append(h)
    if unknown:
        print(f"  [WARN] 未识别的列: {unknown}", file=sys.stderr)
    return mapping


def _row_to_dict(
    row: tuple[Any, ...],
    col_map: dict[int, str],
    row_num: int,
) -> dict[str, Any] | str:
    record: dict[str, Any] = {}
    for idx, key in col_map.items():
        val = row[idx] if idx < len(row) else None
        if key in ("min_rank", "enrollment_count"):
            try:
                val = int(float(str(val).strip())) if val is not None and str(val).strip() else 0
            except (ValueError, TypeError):
                return f"第{row_num}行: 列'{key}'值'{val}'无法解析为整数"
        elif key == "min_score":
            try:
                val = float(str(val).strip()) if val is not None and str(val).strip() else 0.0
            except (ValueError, TypeError):
                return f"第{row_num}行: 列'{key}'值'{val}'无法解析为数字"
        elif key == "year":
            try:
                val = int(float(str(val).strip()))
            except (ValueError, TypeError):
                return f"第{row_num}行: 列'year'值'{val}'无法解析为年份"
        elif key in ("college_id", "major_id", "province", "batch"):
            val = str(val).strip() if val else ""
        record[key] = val

    for rk in REQUIRED_KEYS:
        if rk not in record or not record[rk]:
            return f"第{row_num}行: 缺少必填列'{rk}'"

    for ok in OPTIONAL_KEYS:
        record.setdefault(ok, "" if ok == "batch" else 0)

    return record


def _validate_year(record: dict[str, Any], row_num: int) -> str | None:
    y = record.get("year", 0)
    if not isinstance(y, int) or y < 2000 or y > 2026:
        return f"第{row_num}行: 年份'{y}'超出合理范围 (2000-2026)"
    return None


def _validate_foreign_keys(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    conn = get_connection()
    valid_colleges = set(
        row[0] for row in conn.execute("SELECT id FROM colleges").fetchall()
    )
    valid_majors = set(
        row[0] for row in conn.execute("SELECT id FROM majors").fetchall()
    )
    conn.close()

    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, r in enumerate(records):
        row_num = i + 2
        cid = r.get("college_id", "")
        mid = r.get("major_id", "")
        if cid and cid not in valid_colleges:
            errors.append(f"第{row_num}行: college_id '{cid}' 在 colleges 表中不存在")
            continue
        if mid and mid not in valid_majors:
            errors.append(f"第{row_num}行: major_id '{mid}' 在 majors 表中不存在")
            continue
        valid.append(r)
    return valid, errors


def read_excel(path: Path, sheet_name: str | None) -> list[dict[str, Any]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet_name:
        ws = wb[sheet_name]
    else:
        ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    headers = [str(c or "").strip() for c in rows[0]]
    col_map = _resolve_columns(headers)

    missing = [k for k in REQUIRED_KEYS if k not in col_map.values()]
    if missing:
        raise ValueError(
            f"缺少必填列: {missing}。当前列名: {headers}\n"
            f"支持的列名: {', '.join(sorted(COLUMN_ALIASES))}"
        )

    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx, row in enumerate(rows[1:], start=2):
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        result = _row_to_dict(row, col_map, idx)
        if isinstance(result, str):
            errors.append(result)
            continue
        ve = _validate_year(result, idx)
        if ve:
            errors.append(ve)
            continue
        parsed.append(result)

    return parsed, errors


def read_csv(path: Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        raw_rows = list(reader)

    if not raw_rows:
        return [], []

    headers = [h.strip() for h in raw_rows[0]]
    col_map = _resolve_columns(headers)

    missing = [k for k in REQUIRED_KEYS if k not in col_map.values()]
    if missing:
        raise ValueError(
            f"缺少必填列: {missing}。当前列名: {headers}\n"
            f"支持的列名: {', '.join(sorted(COLUMN_ALIASES))}"
        )

    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx, row in enumerate(raw_rows[1:], start=2):
        if all(v.strip() == "" for v in row):
            continue
        result = _row_to_dict(tuple(row), col_map, idx)
        if isinstance(result, str):
            errors.append(result)
            continue
        ve = _validate_year(result, idx)
        if ve:
            errors.append(ve)
            continue
        parsed.append(result)

    return parsed, errors


def run():
    parser = argparse.ArgumentParser(
        description="批量导入录取位次数据（admission_ranks 表）"
    )
    parser.add_argument(
        "--file", "-f", required=True, type=str,
        help="Excel (.xlsx) 或 CSV (.csv) 文件路径",
    )
    parser.add_argument(
        "--sheet", "-s", type=str, default=None,
        help="Excel 工作表名称（默认: 第一个工作表）",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="跳过外键校验（导入前确保数据正确时使用）",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[ERROR] 文件不存在: {path}")
        sys.exit(1)

    print(f"正在读取: {path}")
    t0 = time.time()

    init_db()

    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        parsed, parse_errors = read_excel(path, args.sheet)
    elif suffix == ".csv":
        parsed, parse_errors = read_csv(path)
    else:
        print(f"[ERROR] 不支持的文件格式: {suffix}（支持 .xlsx, .csv）")
        sys.exit(1)

    if parse_errors:
        print(f"\n[WARN] 解析错误 ({len(parse_errors)} 条):")
        for e in parse_errors[:20]:
            print(f"  {e}")
        if len(parse_errors) > 20:
            print(f"  ... 还有 {len(parse_errors) - 20} 条错误")

    if not parsed:
        print("[ERROR] 没有有效数据可导入")
        sys.exit(1)

    if not args.skip_validation:
        print(f"\n正在校验外键 ({len(parsed)} 条)...")
        parsed, fk_errors = _validate_foreign_keys(parsed)
        if fk_errors:
            print(f"[WARN] 外键校验失败 ({len(fk_errors)} 条):")
            for e in fk_errors[:20]:
                print(f"  {e}")
            if len(fk_errors) > 20:
                print(f"  ... 还有 {len(fk_errors) - 20} 条")

    if not parsed:
        print("[ERROR] 外键校验后无有效数据可导入")
        sys.exit(1)

    print(f"\n正在写入数据库 ({len(parsed)} 条)...")
    count = bulk_import_ranks(parsed)
    elapsed = time.time() - t0

    print(f"\n✅ 导入完成!")
    print(f"   总行数:     {len(parsed) + len(parse_errors)}")
    print(f"   成功导入:   {count}")
    print(f"   跳过/错误:  {len(parse_errors) + len(fk_errors) if not args.skip_validation else len(parse_errors)}")
    print(f"   耗时:       {elapsed:.2f}s")


if __name__ == "__main__":
    run()
