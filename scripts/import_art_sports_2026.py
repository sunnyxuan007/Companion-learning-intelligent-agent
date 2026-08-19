#!/usr/bin/env python3
"""导入 2026 广东艺体类本科投档数据（附件3-9，7 类）到 admission_ranks。

数据源：附件3 体育 / 附件4 音乐 / 附件5 舞蹈 / 附件6 美术与设计 /
       附件7 书法 / 附件8 播音与主持 / 附件9 表(导)演
列：院校代码(广东地方码) 院校名称 专业组代码 计划数 投档人数 投档最低分 投档最低排位

写入约定：
- exam_category='艺体类'，batch='艺体类本科批'，art_category=类别，rank_source='official'
- major_id='GEN'（组级投档，无专业明细）
- 地方码 → 官方码（college_code_map）；缺失 4 所 2026 新设院校自动补 colleges 行 + map

用法：python scripts/import_art_sports_2026.py [--dry-run]
"""

from __future__ import annotations

import glob
import os
import sys

from deeptutor.services.custom.db import get_connection, init_db

DATA_DIR = "/home/sunnyxuan2/桌面/data for agent"

# 附件文件 → 艺体类别
ART_FILES: list[tuple[str, str]] = [
    ("附件3 广东省2026年本科体育类投档情况", "体育"),
    ("附件4 广东省2026年本科音乐类统考投档情况", "音乐"),
    ("附件5 广东省2026年本科舞蹈类统考投档情况", "舞蹈"),
    ("附件6 广东省2026年本科美术与设计类统考投档情况", "美术与设计"),
    ("附件7 广东省2026年本科书法类统考投档情况", "书法"),
    ("附件8 广东省2026年本科播音与主持类统考投档情况", "播音与主持"),
    ("附件9 广东省2026年本科表(导)演类统考投档情况", "表（导）演"),
]

# 2026 新设/未入库院校：地方码 → (官方码, 省份, 城市, 名称)
MISSING_COLLEGES: dict[str, dict[str, str]] = {
    "11775": {"official_code": "4113011775", "province": "河北", "city": "三河", "name": "防灾科技学院"},
    "14831": {"official_code": "4141014831", "province": "河南", "city": "郑州", "name": "郑州美术学院"},
    "14879": {"official_code": "4141014879", "province": "河南", "city": "郑州", "name": "河南体育学院"},
    "14985": {"official_code": "4151014985", "province": "四川", "city": "资阳", "name": "成都美术学院"},
}

# 校区变体地方码 → 官方码（college_code_map 里已有错误映射的需覆盖）
VARIANT_MAP: dict[str, str] = {
    "19027": "4111010027-ZH",  # 北师大(珠海校区)，非本部 4111010027
}


def resolve_official_code(conn, local_code: str, school_name: str) -> tuple[str, bool]:
    """地方码 → 官方码。缺失时补 colleges + map，返回 (官方码, is_new)。"""
    if local_code in VARIANT_MAP:
        official = VARIANT_MAP[local_code]
        conn.execute(
            """INSERT OR REPLACE INTO college_code_map
               (official_code, province_code, province, school_name, source)
               VALUES (?, ?, '广东', ?, 'gd_art_variant')""",
            (official, local_code, school_name),
        )
        return official, False

    row = conn.execute(
        "SELECT official_code FROM college_code_map WHERE province=? AND province_code=?",
        ("广东", local_code),
    ).fetchone()
    if row and row["official_code"]:
        return row["official_code"], False

    # 直接匹配官方码后 5 位 = 地方码（规则映射）
    hit = conn.execute(
        "SELECT id FROM colleges WHERE id LIKE ? AND length(id) = 10",
        (f"%{local_code}",),
    ).fetchone()
    if hit:
        official = hit["id"]
        conn.execute(
            """INSERT OR REPLACE INTO college_code_map
               (official_code, province_code, province, school_name, source)
               VALUES (?, ?, '广东', ?, 'gd_art_2026')""",
            (official, local_code, school_name),
        )
        return official, False

    # 缺失院校（2026 新设）
    if local_code in MISSING_COLLEGES:
        meta = MISSING_COLLEGES[local_code]
        official = meta["official_code"]
        exists = conn.execute("SELECT 1 FROM colleges WHERE id=?", (official,)).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO colleges (id, name, province, city, type, level, is_public, tags,
                   dorm_score, city_vitality, cost_index, employment_rate, avg_salary, region, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, strftime('%s','now'), strftime('%s','now'))""",
                (official, meta["name"], meta["province"], meta["city"], "艺术", "普通", 1, None,
                 6.0, 6.0, 5.0, 0.85, 12000, None),
            )
            conn.execute(
                """INSERT OR REPLACE INTO college_code_map
                   (official_code, province_code, province, school_name, source)
                   VALUES (?, ?, '广东', ?, 'gd_art_2026')""",
                (official, local_code, meta["name"]),
            )
        return official, True

    raise ValueError(f"无法映射地方码 {local_code}（{school_name}）")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    init_db()
    conn = get_connection()

    total_rows = 0
    total_new_groups = 0
    inserted = 0
    skipped_dup = 0
    errors: list[str] = []
    new_colleges: set[str] = set()

    for pattern, art_category in ART_FILES:
        matches = glob.glob(os.path.join(DATA_DIR, pattern + "*"))
        if not matches:
            errors.append(f"未找到 {pattern} 文件")
            continue
        path = matches[0]
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]

        cat_rows = 0
        for row in ws.iter_rows(min_row=3, values_only=True):
            if not row or row[0] is None:
                continue
            local_code = str(int(row[0])) if isinstance(row[0], (int, float)) else str(row[0])
            school_name = str(row[1] or "").strip()
            group_code = str(row[2] or "").strip()
            plan_count = int(row[3] or 0)
            投档人数 = int(row[4] or 0)

            def _num(v: object, default: int = 0) -> int:
                if v is None:
                    return default
                if isinstance(v, str):
                    v = v.strip()
                    if v in ("", "-", "/", "—"):
                        return default
                    try:
                        return int(float(v))
                    except ValueError:
                        return default
                return int(v)

            min_score = float(_num(row[5]))
            min_rank = int(_num(row[6]))

            try:
                official, is_new = resolve_official_code(conn, local_code, school_name)
            except ValueError as e:
                errors.append(str(e))
                continue

            if is_new:
                new_colleges.add(official)

            total_rows += 1
            cat_rows += 1
            cur = conn.execute(
                """SELECT 1 FROM admission_ranks
                   WHERE college_id=? AND major_id='GEN' AND province='广东' AND year=2026
                     AND exam_category='艺体类' AND batch='艺体类本科批'
                     AND group_code=? AND art_category=?""",
                (official, group_code, art_category),
            ).fetchone()
            if cur:
                skipped_dup += 1
                continue

            if not dry_run:
                conn.execute(
                    """INSERT OR REPLACE INTO admission_ranks
                       (college_id, major_id, province, year, batch, min_rank, min_score,
                        enrollment_count, exam_category, group_code, rank_source, art_category)
                       VALUES (?, 'GEN', '广东', 2026, '艺体类本科批', ?, ?, ?, '艺体类', ?, 'official', ?)""",
                    (official, min_rank, min_score, 投档人数, group_code, art_category),
                )
                inserted += 1
            else:
                inserted += 1
            total_new_groups += 1
        wb.close()
        print(f"  {art_category}: {cat_rows} 行")

    if not dry_run:
        conn.commit()

    print(f"\n合计 {len(ART_FILES)} 个附件，{total_rows} 行（{total_new_groups} 新组，{skipped_dup} 重复跳过）")
    print(f"插入: {inserted}（{'dry-run，未写库' if dry_run else '已写入'}）")
    if new_colleges:
        print("新补院校:", sorted(new_colleges))
    if errors:
        print("\n错误:")
        for e in errors[:20]:
            print("  ", e)
    conn.close()


if __name__ == "__main__":
    main()