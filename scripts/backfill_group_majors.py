"""补 9 个专业组内专业明细（2026 广东官方组号拆分）。

背景：2026 广东投档表含 GEN 位次但无专业明细的专业组（高校专项/新设组），
专家版 Excel 组号与官方组号不一致（如哈理工 Excel 205 组 = 官方 204/205/208-213 合并）。
本脚本按《2026广东专业目录更正表》的官方组号专业清单，
给 admission_ranks 补 year=2026 的专业行（min_rank=0，用组级位次兜底）。

用法：python scripts/backfill_group_majors.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from deeptutor.services.custom.db import get_connection

# 官方组号 → 专业清单（major_id, 计划数）
# 数据源：《2026广东专业目录更正表》（院校代码/官方组号权威）
BACKFILL = {
    "4123010214": {  # 哈尔滨理工大学（物理）
        "208": [("033", 12)],  # 建筑学
        "209": [("008", 12), ("009", 12), ("010", 12), ("013", 4), ("028", 2)],
        "210": [("011", 24)],
        "211": [("012", 10), ("016", 16), ("017", 2), ("018", 10), ("022", 7),
                ("023", 4), ("031", 4), ("034", 10), ("035", 8)],
        "212": [("014", 8), ("015", 4), ("021", 4), ("029", 36), ("030", 20),
                ("032", 4), ("037", 3)],
        "213": [("024", 2), ("025", 5), ("026", 5)],
    },
    "4132010288": {  # 南京理工大学（物理）— 203 拆出 205
        "205": [("005", 1), ("006", 1), ("007", 1), ("008", 1)],
    },
    "4151010636": {  # 四川师范大学（物理）
        "222": [("035", 1)],  # 数学与应用数学(中外)
        "223": [("041", 1)],  # 英语(中外)
    },
    "4144011847": {  # 佛山大学（物理）— PDF 409 页定向精解，计划合计=GEN
        "205": [("029", 160), ("030", 35), ("031", 40), ("032", 80), ("033", 130),
                ("034", 80), ("035", 25), ("036", 40), ("037", 15), ("038", 60),
                ("039", 35)],  # 合计 700
        "210": [("047", 80), ("048", 80)],  # 合计 160
    },
    "4144010588": {  # 广东技术师范大学（物理）— PDF 291 页定向精解
        "204": [("014", 30)],  # 电气工程及其自动化(职教师资创新实验班)
    },
}

EXAM_CATEGORY = "物理"
PROVINCE = "广东"
BATCH = "本科批"
YEAR = 2026


def main() -> int:
    conn = get_connection()
    n = 0
    for cid, groups in BACKFILL.items():
        for gc, majors in groups.items():
            row = conn.execute(
                "SELECT 1 FROM admission_ranks WHERE college_id=? AND group_code=? AND major_id='GEN' AND year=?",
                (cid, gc, YEAR),
            ).fetchone()
            if not row:
                print(f"!! 缺 GEN 行：{cid} g{gc}，跳过")
                continue
            for mid, plan in majors:
                conn.execute(
                    """INSERT OR REPLACE INTO admission_ranks
                       (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (cid, mid, PROVINCE, YEAR, BATCH, 0, 0, plan, EXAM_CATEGORY, gc),
                )
                n += 1
    conn.commit()
    print(f"已补 {n} 条专业行")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())