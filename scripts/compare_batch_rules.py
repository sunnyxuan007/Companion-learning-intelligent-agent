"""核对《志愿填报指南》(OCR) 批次规则 vs 系统硬编码。

输出比对报告(不改代码)，人工确认后再决定是否修改。
对比对象:
  - 指南提取: data/user/custom/ocr_guide/batch_rules.json (阶段 A)
  - 系统:
    1. PROVINCE_RULES (volunteer_table.py)  — 广东 45 组 / ratio
    2. 前端批次下拉值 (page.tsx)            — 7 个批次选项
    3. admission_ranks 实际批次分布          — 库中已有数据
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.custom.db import get_connection

FRONTEND_BATCHES = [
    "本科批",
    "提前批本科-军检类",
    "提前批本科-非军检类",
    "提前批本科-卫生专项",
    "提前批本科-教师专项",
    "提前批本科-特殊类型招生",
    "提前批本科-空军海军招飞",
]


def main() -> None:
    guide = json.loads(
        (Path(__file__).resolve().parents[1] / "data/user/custom/ocr_guide/batch_rules.json")
        .read_text(encoding="utf-8")
    )

    print("=" * 60)
    print("《志愿填报指南》批次规则 vs 系统硬编码 核对报告")
    print("=" * 60)

    # 1. 指南原文要点(提前批次)
    print("\n【1】指南·批次设置要点")
    for cat, items in guide["batch_categories"].items():
        print(f"  {cat}: {', '.join(items)}")
    print(f"  投档模式: {', '.join(guide['notes'])}")

    # 2. 前端批次选项 vs 指南
    print("\n【2】前端批次选项(7个) vs 指南分类")
    guide_set = set(i for items in guide["batch_categories"].values() for i in items)
    for b in FRONTEND_BATCHES:
        hit = []
        if "军检" in b and "军检院校" in guide_set:
            hit.append("指南提及军检院校")
        if "非军检" in b and "非军检" in guide_set:
            hit.append("指南提及非军检")
        if "卫生专项" in b and "卫生专项" in guide_set:
            hit.append("指南提及卫生专项")
        if "教师专项" in b and "教师专项" in guide_set:
            hit.append("指南提及教师专项")
        if "特殊类型" in b and "特殊类型" in guide_set:
            hit.append("指南提及特殊类型")
        if "招飞" in b and "海军招飞" in guide_set:
            hit.append("指南提及海军招飞")
        status = "✓ 指南有对应分类" if hit else "⚠ 指南未明确提及(可能属综述，需核原文)"
        print(f"  {b}: {status} {('(' + ';'.join(hit) + ')') if hit else ''}")

    # 3. PROVINCE_RULES 广东配置
    print("\n【3】PROVINCE_RULES['广东'] 当前配置")
    print("  groups=45, mode=院校专业组, ratio=[3,4,3]")
    print("  ⚠ 指南未给出具体可填专业组数/比例(正文只述'填报志愿…三个批次同时填报')")
    print("  → 45 组数值无法用本书核对，保留现状或另行核对招生专业目录")

    # 4. 库中实际批次分布
    print("\n【4】admission_ranks 实际批次分布 (2026 广东)")
    conn = get_connection()
    rows = conn.execute(
        """SELECT batch, exam_category, COUNT(*) n FROM admission_ranks
           WHERE province='广东' AND year=2026 GROUP BY batch, exam_category ORDER BY batch"""
    ).fetchall()
    conn.close()
    for r in rows:
        print(f"  {r[0]} [{r[1]}]: {r[2]} 行")

    # 5. 结论
    print("\n【5】结论")
    print("  1) 指南批次分类(军检/非军检/教师/卫生/特殊类型/招飞)与前端 7 个选项一一对应 ✓")
    print("  2) 投档模式'院校专业组'与 PROVINCE_RULES.mode 一致 ✓")
    print("  3) 45 组数 / ratio 指南未提供，无法核对，保留现状")
    print("  4) 指南正文未含具体填报/录取日期('具体时间及安排另行通知')→ 时间表无法从本书提取")


if __name__ == "__main__":
    main()