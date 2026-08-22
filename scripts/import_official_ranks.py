"""导入官方投档情况表（2025 提前批 + 2025/2026 艺体统考 + 2026 提前批）。

数据源：桌面 data for agent 下 2025/2026 年官方投档表（7 列标准格式：
院校代码/院校名称/专业组代码/计划数/投档人数/投档最低分/投档最低排位）。

预测口径（AGENTS.md Phase 23.2）：填报 N 年用 N-1 及更早录取位次 + N 年一分一段。
- 2025 表 → 作为 2026 预测的评分基准（year=2025）
- 2026 表 → 存档（year=2026），评分引擎自动排除目标年；目标年=2027 时生效

规则：
- 征集志愿表跳过
- 同名重复文件（含“(1)”后缀）跳过
- 导入前先删除该 (batch, year, exam_category, art_category) 的旧行（旧数据为
  专家版 Excel 组号体系，与官方投档表组号不一致，必须替换）
- 幂等：重复运行效果一致

用法：python scripts/import_official_ranks.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

DATA_DIR = Path.home() / "桌面/data for agent"

ART_CATS = {
    "美术与设计类": "美术与设计",
    "表(导)演类": "表（导）演",
    "表(导)演": "表（导）演",
    "播音与主持类": "播音与主持",
    "播音与主持": "播音与主持",
    "书法类": "书法",
    "音乐类": "音乐",
    "舞蹈类": "舞蹈",
    "体育类": "体育",
    "体育": "体育",
}

ART_PATTERN = re.compile(
    r"(美术与设计类|表\(导\)演类?|播音与主持类?|书法类|音乐类|舞蹈类|体育类?)"
)

# 投档表地方码 → 官方码补充映射（港澳高校本部/军警/艺术院校，不在广东 college_code_map）
EXTRA_MAP = {
    "10728": "4161010728",  # 西安音乐学院
    "81002": "81002",       # 香港中文大学（本部，港澳高校）
    "81006": "81006",       # 香港城市大学（本部）
    "92036": "92036",       # 联勤保障部队工程大学
}

# 投档表出现的库中缺失院校（创建行）
NEW_COLLEGES = {
    "81006": ("香港城市大学", "香港", "综合", "普通"),
}


def classify(name: str) -> tuple[int, str, str, str] | None:
    """返回 (year, batch, exam_category, art_category)；art_category 为空串表示普通类。"""
    m = re.search(r"广东省(2025|2026)年", name)
    if not m:
        return None
    year = int(m.group(1))
    if "征集志愿" in name:
        return None
    if "(1)" in name:
        return None

    if "提前批" in name:
        if "普通类" in name:
            cat = "物理" if ("物理" in name) else "历史"
            if "非军检" in name:
                return (year, "提前批本科-非军检类", cat, "")
            if "军检" in name:
                return (year, "提前批本科-军检类", cat, "")
            if "卫生专项" in name:
                return (year, "提前批本科-卫生专项", cat, "")
            if "教师专项" in name:
                return (year, "提前批本科-教师专项", cat, "")
            if "特殊类型" in name:
                return (year, "提前批本科-特殊类型招生", cat, "")
            if "招飞" in name:
                return (year, "提前批本科-空军海军招飞", cat, "")
            return None
        # 提前批艺体（教师专项/体育特殊类型）
        am = ART_PATTERN.search(name)
        art = ART_CATS.get(am.group(1), "") if am else ""
        if "特殊类型" in name:
            return (year, "提前批本科-特殊类型招生", "艺体类", art)
        if "教师专项" in name:
            return (year, "提前批本科-教师专项", "艺体类", art)
        return None

    # 普通批艺体统考
    if "本科" in name and "投档情况" in name:
        am = ART_PATTERN.search(name)
        if am and am.group(1) in ART_CATS:
            return (year, "艺体类本科批", "艺体类", ART_CATS[am.group(1)])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_custom_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    code_map = {
        r["province_code"]: r["official_code"]
        for r in conn.execute(
            "SELECT province_code, official_code FROM college_code_map WHERE province='广东'"
        ).fetchall()
    }
    code_map.update(EXTRA_MAP)

    if not args.dry_run:
        for cid, (name, prov, ctype, level) in NEW_COLLEGES.items():
            conn.execute(
                """INSERT OR IGNORE INTO colleges
                   (id, name, province, city, type, level, is_public, created_at, updated_at)
                   VALUES (?, ?, ?, '', ?, ?, 1, strftime('%s','now'), strftime('%s','now'))""",
                (cid, name, prov, ctype, level),
            )
        for pcode, ocode in EXTRA_MAP.items():
            conn.execute(
                "INSERT OR IGNORE INTO college_code_map (official_code, province_code, province, school_name, source) VALUES (?, ?, '广东', '', 'official_ranks_2025')",
                (ocode, pcode),
            )
        conn.commit()

    files = sorted(DATA_DIR.glob("*.xlsx"))
    imported = 0
    deleted = 0
    skipped_no_map = 0
    stats: dict[tuple, int] = {}
    for f in files:
        meta = classify(f.name)
        if meta is None:
            continue
        year, batch, exam_category, art_category = meta
        if exam_category == "艺体类" and not art_category:
            continue
        # 2026 艺体统考已随附件3-9 导入（含组内专业明细），跳过以免清掉专业行
        if year == 2026 and batch == "艺体类本科批":
            continue

        wb = openpyxl.load_workbook(f, read_only=True)
        ws = wb.active
        rows = []
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            if i < 2:
                continue
            if not r or not r[0]:
                continue
            local = str(r[0] or "").strip()
            gcode = str(r[2] or "").strip()
            plan = int(r[3]) if r[3] not in (None, "", "-") else 0
            min_score = float(r[5]) if r[5] not in (None, "", "-") else 0.0
            min_rank = int(r[6]) if r[6] not in (None, "", "-") else 0
            off = code_map.get(local)
            if not off:
                skipped_no_map += 1
                continue
            rows.append((off, gcode, plan, min_score, min_rank))
        wb.close()

        if not args.dry_run:
            if art_category:
                conn.execute(
                    "DELETE FROM admission_ranks WHERE province='广东' AND year=? AND batch=? AND exam_category=? AND art_category=?",
                    (year, batch, exam_category, art_category),
                )
            else:
                conn.execute(
                    "DELETE FROM admission_ranks WHERE province='广东' AND year=? AND batch=? AND exam_category=? AND art_category=''",
                    (year, batch, exam_category),
                )
        for off, gcode, plan, min_score, min_rank in rows:
            if not args.dry_run:
                conn.execute(
                    """INSERT OR REPLACE INTO admission_ranks
                       (college_id, major_id, province, year, batch, min_rank, min_score,
                        enrollment_count, exam_category, group_code, rank_source, art_category)
                       VALUES (?, 'GEN', '广东', ?, ?, ?, ?, ?, ?, ?, 'official', ?)""",
                    (off, year, batch, min_rank, min_score, plan, exam_category, gcode, art_category),
                )
            stats[(year, batch, exam_category, art_category)] = stats.get(
                (year, batch, exam_category, art_category), 0
            ) + 1
            imported += 1
        deleted += 1
        print(f"  {f.name[:50]:52} → {year} {batch} [{exam_category}{'+' + art_category if art_category else ''}] {len(rows)} 行")

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\n合计导入 GEN 行: {imported} | 删除旧批次单元: {deleted} | 未匹配院校码: {skipped_no_map}")
    for k, v in sorted(stats.items()):
        print(f"  {k} = {v} 行")
    if args.dry_run:
        print("(--dry-run 未写入)")
    return 0


if __name__ == "__main__":
    sys.exit(main())