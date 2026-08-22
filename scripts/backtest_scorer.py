"""录取位次预测回测（只读）。

口径（AGENTS.md Phase 23.2）：填报 N 年 = 用 N-1 及更早录取位次 + N 年一分一段表。
本脚本用 N-1/N-2/N-3 年组级最低位次加权预测 N 年位次，与 N 年实际投档位次对比。

用法：
  python scripts/backtest_scorer.py --target 2026 --batch 本科批 [--cat 物理|历史|全部]
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

BATCH_ALIAS = {
    "本科批": {"current": "本科批", "history": "本科批次"},
}


def stats(pred: list[tuple[float, float]]) -> str:
    n = len(pred)
    if n == 0:
        return "无样本"
    mae = sum(abs(p - a) for p, a in pred) / n
    w = lambda th: 100.0 * sum(1 for p, a in pred if abs(p - a) / (a or 1) < th) / n
    return f"样本={n} MAE位次={mae:.0f} | 误差<10%: {w(0.10):.1f}% | <20%: {w(0.20):.1f}% | <30%: {w(0.30):.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=2026)
    ap.add_argument("--cat", default="全部", choices=["物理", "历史", "全部"])
    ap.add_argument("--w1", type=float, default=0.7)
    ap.add_argument("--w2", type=float, default=0.2)
    ap.add_argument("--w3", type=float, default=0.1)
    args = ap.parse_args()

    conn = sqlite3.connect(get_custom_db_path())
    conn.row_factory = sqlite3.Row
    cats = [args.cat] if args.cat != "全部" else ["物理", "历史"]

    for cat in cats:
        yr: dict[tuple, dict[int, int]] = collections.defaultdict(dict)
        for r in conn.execute(
            """SELECT college_id, group_code, year, MIN(min_rank) rk FROM admission_ranks
               WHERE province='广东' AND exam_category=? AND group_code!='' AND min_rank>0
               AND ((year = ? AND batch = '本科批') OR (year < ? AND year >= ? AND batch = '本科批次'))
               GROUP BY college_id, group_code, year""",
            (cat, args.target, args.target, args.target - 3),
        ).fetchall():
            yr[(r["college_id"], r["group_code"])][r["year"]] = r["rk"]

        rows = []
        for d in yr.values():
            if args.target not in d or (args.target - 1) not in d:
                continue
            fill = d[args.target - 1]
            p = sum(
                w * d.get(y, fill)
                for w, y in ((args.w1, args.target - 1), (args.w2, args.target - 2), (args.w3, args.target - 3))
            )
            rows.append((p, d[args.target]))
        print(f"{cat} 预测 {args.target}（权重 {args.w1}/{args.w2}/{args.w3}，历史 year < {args.target}）: {stats(rows)}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())