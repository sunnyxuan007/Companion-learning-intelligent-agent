"""从《广东省2026年普通高等学校志愿填报指南》OCR 产物(DOCX)提取结构化信息。

提取三块内容到 data/user/custom/ocr_guide/:
  1. policy_sections.json   — 按章节分段的政策正文(1-4章)
  2. batch_rules.json       — 第二章批次设置结构化(提前/本科/专科 + 分类)
  3. medical_rules.json     — 第三章体检限制表(色觉/视力/听力 → 受限专业)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import docx

DOCX_PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "/home/sunnyxuan2/桌面/data for agent/（已压缩）"
    "广东省2026年普通高等学校志愿填报指南2026.6.10_20260818100935.docx"
)
OUT_DIR = Path(__file__).resolve().parents[1] / "data/user/custom/ocr_guide"


def _clean(t: str) -> str:
    t = t.replace("\u3000", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def extract_paragraphs(path: str) -> list[str]:
    d = docx.Document(path)
    paras: list[str] = []
    for p in d.paragraphs:
        t = _clean(p.text)
        if t:
            paras.append(t)
    return paras


def split_chapters(paras: list[str]) -> dict[str, list[str]]:
    """按章标题切分正文段落(第一章..第四章)，保留原顺序。"""
    chapters: dict[str, list[str]] = {}
    order: list[str] = []
    cur: str | None = None
    for t in paras:
        m = re.match(r"^第[一二三四五]章\s*[、.]?\s*(.{2,20})$", t)
        if m:
            cur = m.group(0)
            if cur not in chapters:
                chapters[cur] = []
                order.append(cur)
            continue
        if cur:
            chapters[cur].append(t)
        else:
            chapters.setdefault("_front", []).append(t)
    return chapters, order


def extract_batch_rules(paras: list[str]) -> dict:
    """从第二章段落提取批次设置结构。"""
    joined = "\n".join(paras)
    rules: dict = {"batch_hierarchy": [], "batch_categories": {}, "notes": []}

    # 提前批次包含内容(第197段后连续多段)
    for kw in ("空军", "海军招飞", "军检院校", "非军检", "教师专项", "卫生专项",
               "高水平运动队", "综合评价", "特殊类型", "专科提前", "定向培养军士"):
        if kw in joined:
            rules["batch_categories"].setdefault("提前批次", []).append(kw)
    for kw in ("高校专项", "地方专项", "少数民族班", "预科班", "艺体类本科"):
        if kw in joined:
            rules["batch_categories"].setdefault("本科批次", []).append(kw)
    for kw in ("普通类专科", "艺体类专科"):
        if kw in joined:
            rules["batch_categories"].setdefault("专科(高职)批次", []).append(kw)

    # 投档模式关键词
    for kw in ("院校专业组投档录取模式", "平行志愿", "非平行志愿", "顺序志愿",
               "梯度志愿", "分开划线", "分开投档录取"):
        if kw in joined:
            rules["notes"].append(kw)

    return rules


def extract_medical_rules(doc) -> list[dict]:
    """从第三章体检表(DOCX 表格 2/3/4)提取限制 → 受限专业映射。"""
    rules: list[dict] = []
    for t in doc.tables:
        if len(t.columns) < 3:
            continue
        rows = t.rows
        if not rows:
            continue
        # 跳过表头(第一列含"疾病或生理缺陷")
        for row in rows:
            cells = [_clean(c.text) for c in row.cells]
            if not cells or not cells[0]:
                continue
            if "疾病或生理缺陷" in cells[0]:
                continue
            rules.append({
                "condition": cells[0],
                "standard_ref": cells[1] if len(cells) > 1 else "",
                "restricted": cells[2] if len(cells) > 2 else "",
            })
    return rules


def main() -> None:
    paras = extract_paragraphs(DOCX_PATH)
    print(f"非空段落数: {len(paras)}")

    chapters, order = split_chapters(paras)
    print(f"章节: {order}")

    batch_rules = extract_batch_rules(paras)
    medical_rules = extract_medical_rules(docx.Document(DOCX_PATH))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 政策章节
    policy_sections = []
    for ch in order:
        body = "\n".join(chapters[ch])
        policy_sections.append({
            "title": ch,
            "content": body[:3000],
        })
    (OUT_DIR / "policy_sections.json").write_text(
        json.dumps(policy_sections, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"政策章节: {len(policy_sections)} 段 → policy_sections.json")

    # 2. 批次规则
    (OUT_DIR / "batch_rules.json").write_text(
        json.dumps(batch_rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"批次规则: {json.dumps(batch_rules, ensure_ascii=False)[:200]} → batch_rules.json")

    # 3. 体检规则
    (OUT_DIR / "medical_rules.json").write_text(
        json.dumps(medical_rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"体检限制: {len(medical_rules)} 条 → medical_rules.json")

    # 摘要
    total_chars = sum(len(p["content"]) for p in policy_sections)
    print(f"政策正文总字符: {total_chars}")


if __name__ == "__main__":
    main()