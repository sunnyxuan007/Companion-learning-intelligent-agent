"""Import 广东省 2026 艺体类一分一段（分数段统计表）Excel -> score_rank_segments.

- 共 14 个文件（附件 3-16）：体育/美术/音乐(5 方向)/舞蹈/表导(3 方向)/播音(2 方向)/书法
- 列结构有两种：`合成总分, 本科(人数,累计), 专科(人数,累计)` 或
  `合成总分, None, 本科人数, 本科累计, 专科人数, 专科累计`（数据起始行因文件而异）
- exam_category 用方向码（如 `音乐表演(声乐)`），与 art_category 解耦，保证细分排名精确
- 仅写入 year=2026，不动历史行（INSERT OR REPLACE 按主键覆盖同 year 行）
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from deeptutor.services.custom.db import get_connection, init_db

PROVINCE = "广东"
YEAR = 2026

DIR = Path("/home/sunnyxuan2/桌面/data for agent")

# 附件号 → (文件名片段, 方向码)
FILES: list[tuple[str, str]] = [
    ("3.广东省2026年普通高考体育类总分分数段统计表", "体育"),
    ("4.广东省2026年普通高考美术与设计类总分分数段统计表", "美术与设计"),
    ("5.广东省2026年普通高考音乐教育类总分分数段统计表", "音乐教育类"),
    ("6.广东省2026年普通高考音乐教育(声乐主项)方向总分分数段统计表", "音乐教育(声乐主项)"),
    ("7.广东省2026年普通高考音乐教育(器乐主项)方向总分分数段统计表", "音乐教育(器乐主项)"),
    ("8.广东省2026年普通高考音乐表演(声乐)方向总分分数段统计表", "音乐表演(声乐)"),
    ("9.广东省2026年普通高考音乐表演(器乐)方向总分分数段统计表", "音乐表演(器乐)"),
    ("10.广东省2026年普通高考舞蹈类总分分数段统计表", "舞蹈"),
    ("11.广东省2026年普通高考表(导)演(戏剧影视表演)方向总分分数段统计表", "表(导)演(戏剧影视表演)"),
    ("12.广东省2026年普通高考表(导)演(服装表演)方向总分分数段统计表", "表(导)演(服装表演)"),
    ("13.广东省2026年普通高考表(导)演(戏剧影视导演)方向总分分数段统计表", "表(导)演(戏剧影视导演)"),
    ("14.广东省2026年普通高考播音与主持(普通话)方向总分分数段统计表", "播音与主持(普通话)"),
    ("15.广东省2026年普通高考播音与主持(粤语)方向总分分数段统计表", "播音与主持(粤语)"),
    ("16.广东省2026年普通高考书法类总分分数段统计表", "书法"),
]


def _find_data_start(ws) -> int:
    """定位表头行（含 '累计人数'）之后的数据起始行。"""
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        vals = [str(x) for x in row if x is not None]
        if any("累计人数" in v for v in vals):
            return i  # 1-based，下一行即数据
    raise ValueError("未找到 '累计人数' 表头")


def _strip_above(value: object) -> int:
    """'586（含以上）' -> 586；'564' -> 564。"""
    s = str(value).strip()
    for mark in ("（含以上）", "(含以上)", "含以上"):
        if mark in s:
            s = s.split(mark)[0]
            break
    return int(float(s))


def _parse(filepath: Path, direction: str) -> list[dict]:
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    start = _find_data_start(ws)
    rows = list(ws.iter_rows(min_row=start, values_only=True))
    wb.close()

    # 找列：本科累计 与 专科累计 所在列
    header = [str(x) if x is not None else "" for x in rows[0]]
    # 表头行可能是 '累计人数' 两列（本科/专科），位置按出现顺序
    cum_cols = [i for i, h in enumerate(header) if "累计人数" in h]
    if len(cum_cols) < 2:
        raise ValueError(f"表头缺累计人数列: {header}")
    undergrad_cum_col = cum_cols[0]
    voc_cum_col = cum_cols[1]

    records: list[dict] = []
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        try:
            s = _strip_above(row[0])
        except (ValueError, TypeError):
            continue
        for col, bc in ((undergrad_cum_col, "本科"), (voc_cum_col, "专科")):
            v = row[col] if col < len(row) else None
            if v is None:
                continue
            try:
                records.append({
                    "province": PROVINCE,
                    "year": YEAR,
                    "exam_category": direction,
                    "score": s,
                    "cumulative_rank": int(float(str(v).strip())),
                    "batch_category": bc,
                })
            except (ValueError, TypeError):
                pass
    return records


def main() -> None:
    init_db()
    conn = get_connection()
    for prefix, direction in FILES:
        # 匹配文件
        matches = [p for p in DIR.glob(f"{prefix}*.xlsx")]
        if not matches:
            print(f"SKIP: 未找到 {prefix}*.xlsx")
            continue
        filepath = matches[0]
        recs = _parse(filepath, direction)
        for r in recs:
            conn.execute(
                """INSERT OR REPLACE INTO score_rank_segments
                   (province, year, exam_category, score, cumulative_rank, batch_category)
                   VALUES (?,?,?,?,?,?)""",
                (r["province"], r["year"], r["exam_category"], r["score"],
                 r["cumulative_rank"], r["batch_category"]),
            )
        conn.commit()
        print(f"{direction}: {filepath.name} -> {len(recs)} 条 (year={YEAR})")

    # 汇总
    print("\n=== 2026 艺体类分段汇总 ===")
    for r in conn.execute(
        "SELECT exam_category, batch_category, COUNT(*), MIN(score), MAX(score), MAX(cumulative_rank) "
        "FROM score_rank_segments WHERE province=? AND year=? GROUP BY exam_category, batch_category "
        "ORDER BY exam_category, batch_category",
        (PROVINCE, YEAR),
    ).fetchall():
        print(f"  {r[0]} [{r[1]}]: {r[2]} 行, 分数 {r[3]}~{r[4]}, 累计到 {r[5]}")
    conn.close()


if __name__ == "__main__":
    main()