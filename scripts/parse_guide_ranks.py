"""试点解析《广东省2026年志愿填报指南》DOCX 中 2025 排位表（物理本科普通批）。

仅解析"行式段落"（段内含 代码+名称+数字 的记录），列式区块（清华等）跳过。
试点目标：验证行式记录能否与 admission_ranks 2025 数据匹配，输出正确率报告。

用法:
    python scripts/parse_guide_ranks.py --docx "<path>" [--out data/user/custom/ocr_guide/guide_ranks_pilot.json]
    python scripts/parse_guide_ranks.py --report   # 仅对已有 JSON 做交叉验证报告
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

DOCX = Path("/home/sunnyxuan2/桌面/data for agent/（已压缩）广东省2026年普通高等学校志愿填报指南2026.6.10_20260818095218.docx")
OUT = Path("data/user/custom/ocr_guide/guide_ranks_pilot.json")

# 本科普通批物理起点：找到 "普通类(物理)本科" 正文标题（非目录）。流式扫描前 60MB。
PHS_BATCH_START_MB = 8.0  # 从 8MB 起找标题，避免目录/提前批
PHS_BATCH_END_MB = 58.0  # 专科起点


def iter_paras(docx: Path, start: int, end: int) -> list[str]:
    """流式读取 document.xml 的 [start,end) 字节段，返回非空段落文本列表。"""
    z = zipfile.ZipFile(docx)
    f = z.open("word/document.xml")
    if start:
        f.seek(start)
    data = f.read(end - start if end > start else -1)
    f.close()
    z.close()
    text = data.decode("utf-8", errors="replace")
    items: list[str] = []
    for para in re.split(r"</w:p>", text):
        ts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para)
        merged = "".join(ts).strip()
        if merged:
            items.append(merged)
    return items


def find_phase_paras(docx: Path) -> tuple[list[str], int | None, int | None]:
    """流式读全文档段落流，定位物理本科普通批范围。

    返回 (items, start_idx, end_idx)。start=首个 '普通类(物理)本科' 正文标题，
    end=首个 '普通类(物理)专科' 标题。
    """
    z = zipfile.ZipFile(docx)
    f = z.open("word/document.xml")
    items: list[str] = []
    start = end = None
    state = "scan"
    CHUNK = 4_000_000
    while True:
        data = f.read(CHUNK)
        if not data:
            break
        text = data.decode("utf-8", errors="replace")
        for para in re.split(r"</w:p>", text):
            ts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para)
            merged = "".join(ts).strip()
            if not merged:
                continue
            items.append(merged)
            cur = len(items) - 1
            if state == "scan":
                # 物理本科普通批正文标题（每页页眉重复出现，取首个即可）
                if re.match(r"^普通类\s*\(?物理\)?\s*本科$", merged):
                    start = cur
                    state = "in_batch"
            elif state == "in_batch":
                if re.match(r"^普通类\s*\(?物理\)?\s*专科", merged):
                    end = cur
                    break
        if end is not None:
            break
    f.close()
    z.close()
    return items, start, end


def parse_row_style(items: list[str], start: int, end: int) -> list[dict]:
    """解析行式段落：识别 院校/专业组/专业 记录，提取代码+名称+尾随数字。

    段落形态:
      10004北京交通大学                   107        → 院校: 代码10004 名北交大 投档数107
      208 专业组208                     90         → 专业组: 代码208 组名 投档数90
      007 与智能制造)                    19        → 专业: 代码007 名 投档数19
    尾随数字(段尾 1-3 个数字块)为投档数/录取数/排位等，取值因行而异。
    仅提取尾随 1 个数字作为主数字（投档数）；多个数字时取全部。
    """
    records: list[dict] = []

    for i in range(start, end):
        t = items[i]
        # 跳过页眉/表头
        if re.match(r"^(普通类|续上表|代\s*码|院饺|院校|本\s*科|投档线|低排位|投\s*档|录\s*取|最\s*低|排位|分\s*$)", t):
            continue

        # 院校行: 5 位代码开头 + 中文名 + 尾随数字
        m = re.match(r"^(\d{5})\s*([\u4e00-\u9fff][\u4e00-\u9fff()（）、·]+?)\s+(\d+(?:\.\d+)?)$", t)
        if m:
            records.append({
                "type": "college",
                "college_code": m.group(1),
                "name": m.group(2),
                "nums": [float(m.group(3))],
            })
            continue

        # 专业组行: 3 位代码 + "专业组N" + 尾随数字
        m = re.match(r"^(\d{3})\s+(专业组\S+?)\s+((?:\d+(?:\.\d+)?\s*)+)$", t)
        if m:
            records.append({
                "type": "group",
                "group_code": m.group(1),
                "name": m.group(2),
                "nums": _parse_nums(m.group(3)),
            })
            continue

        # 专业行: 3 位代码 + 名称 + 尾随数字
        m = re.match(r"^(\d{3})\s+([\u4e00-\u9fffA-Za-z][^0-9]*?)\s+((?:\d+(?:\.\d+)?\s*)+)$", t)
        if m:
            records.append({
                "type": "major",
                "major_code": m.group(1),
                "name": m.group(2),
                "nums": _parse_nums(m.group(3)),
            })
            continue

    return records


def _parse_nums(s: str) -> list[float]:
    return [float(x) for x in s.split() if x]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", type=Path, default=DOCX)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        generate_report(args.out)
        return

    print("定位物理本科普通批段落范围...")
    items, start, end = find_phase_paras(args.docx)
    if start is None:
        print("未找到物理本科普通批标题，退出")
        sys.exit(1)
    print(f"  段落范围: {start} ~ {end}（共 {end - start} 段）")

    # 从起始标题稍后开始（跳过页眉/表头碎行），解析行式记录
    records = parse_row_style(items=items, start=start + 5, end=end)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"解析出 {len(records)} 条行式记录 → {args.out}")


def generate_report(json_path: Path) -> None:
    """加载试点 JSON，与 admission_ranks 2025 比对输出报告。"""
    import sqlite3

    records = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"试点记录数: {len(records)}")
    colleges = [r for r in records if r["type"] == "college"]
    groups = [r for r in records if r["type"] == "group"]
    majors = [r for r in records if r["type"] == "major"]
    print(f"  院校 {len(colleges)} / 专业组 {len(groups)} / 专业 {len(majors)}")

    conn = sqlite3.connect("data/user/custom/deeptutor_custom.db")
    conn.row_factory = sqlite3.Row

    # 1) 院校级匹配：5 位国标码 → 官方码（取 id 最长 = 10 位）
    def get_official(code: str) -> str | None:
        r = conn.execute(
            "SELECT id FROM colleges WHERE id LIKE ? ORDER BY LENGTH(id) DESC",
            (f"%{code}",),
        ).fetchone()
        return r["id"] if r and len(r["id"]) == 10 else None

    matched_col = 0
    with_2025 = 0
    col_miss: list[str] = []
    for rec in colleges:
        off = get_official(rec["college_code"])
        if not off:
            col_miss.append(f"{rec['college_code']} {rec['name']}")
            continue
        matched_col += 1
        r = conn.execute(
            "SELECT 1 FROM admission_ranks WHERE college_id=? AND year=2025 AND exam_category='物理' AND province='广东' LIMIT 1",
            (off,),
        ).fetchone()
        if r:
            with_2025 += 1

    print(f"\n=== 院校级 ===")
    print(f"  国标码→官方码匹配: {matched_col}/{len(colleges)}")
    print(f"  库中 2025 广东物理有数据: {with_2025}/{len(colleges)}")
    if col_miss:
        print(f"  未匹配院校: {col_miss[:10]}")

    # 2) 组号体系：指南组号 vs 库组号（抽查）
    print(f"\n=== 组号体系抽查 ===")
    gcodes = [r["group_code"] for r in groups[:20]]
    print(f"  指南排位表组号样本（前 20）: {gcodes}")
    for rec in colleges[:3]:
        off = get_official(rec["college_code"])
        if not off:
            continue
        db_groups = sorted(r["group_code"] for r in conn.execute(
            "SELECT DISTINCT group_code FROM admission_ranks WHERE college_id=? AND year=2025 AND exam_category='物理'",
            (off,)))
        print(f"  {rec['college_code']} {rec['name']}: 库组号 {db_groups}")

    # 3) 专业级计划数匹配
    print(f"\n=== 专业级计划数匹配 ===")
    stats = {"total": 0, "match": 0, "no_major": 0, "plan_mismatch": 0}
    prev_code = None
    for rec in records:
        if rec["type"] == "college":
            prev_code = rec["college_code"]
            continue
        if rec["type"] != "major" or not prev_code:
            continue
        off = get_official(prev_code)
        if not off:
            continue
        stats["total"] += 1
        mcode, plan = rec["major_code"], rec["nums"][0]
        db = conn.execute(
            "SELECT enrollment_count FROM admission_ranks WHERE college_id=? AND year=2025 AND exam_category='物理' AND major_id=? AND major_id!='GEN' LIMIT 1",
            (off, mcode),
        ).fetchone()
        if not db:
            stats["no_major"] += 1
            continue
        if abs(db["enrollment_count"] - plan) <= max(1, plan * 0.15):
            stats["match"] += 1
        else:
            stats["plan_mismatch"] += 1
    print(f"  专业总数: {stats['total']}")
    print(f"  计划匹配: {stats['match']} ({stats['match'] / max(1, stats['total']):.1%})")
    print(f"  库无此专业: {stats['no_major']}  计划不一致: {stats['plan_mismatch']}")

    conn.close()
    print("\n提示: 完整分析见 data/user/custom/ocr_guide/guide_ranks_report.md")


if __name__ == "__main__":
    main()
