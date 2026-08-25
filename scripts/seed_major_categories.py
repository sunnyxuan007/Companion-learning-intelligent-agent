"""专业大类双维度归类回填（Phase 23.5）。

数据源：教育部《普通高等学校本科专业目录（2026年）》DOCX
解析（已验证 852 专业 / 12 门类）：段落+表格双通道、名称去注释括号、门类标记清洗。

归类（双维度 + 多归属）：
- program_type（优先）：含"中外合作/合作办学"→中外合作；含"试验班/实验班"→试验班；其余 normal
- category 多归属（写 college_major_category 关联表）：
  * 目录注释"可授X或Y学士学位" → X+Y 双归属（枚举门类名正则）
  * 人文科学试验班→文学+历史学+哲学；社会科学试验班→法学+经济学+管理学；
    经济管理试验班→经济学+管理学；工科/理科/文科试验班→单归
  * 普通专业：精确名 → 去括号名 → 包含（目录名⊂专业名，取最长）→ 类名（"计算机类"→工学）
  * 未匹配 → 其他

用法：python scripts/seed_major_categories.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402

CATALOG_DOCX = Path.home() / "桌面/data for agent/教育部普通高等学校本科专业目录2026.docx"

CATEGORIES = ["哲学", "经济学", "法学", "教育学", "文学", "历史学",
              "理学", "工学", "农学", "医学", "管理学", "艺术学", "交叉学科"]
CAT_ALT = "|".join(CATEGORIES)
OTHER = "其他"

TRIAL_RULES = [  # 试验班名称关键词 → 门类列表（多归属）
    (r"人文", ["文学", "历史学", "哲学"]),
    (r"社科|社会科学", ["法学", "经济学", "管理学"]),
    (r"经管|经济管理", ["经济学", "管理学"]),
    (r"医学", ["医学"]),
    (r"工科|技术科学|工程|信息", ["工学"]),
    (r"理科|自然科学|数理", ["理学"]),
    (r"文科", ["文学"]),
]

# 段落格式：`100201K    临床医学`（代码+空白+名称）
PARA_CODE_RE = re.compile(rf"^(0[1-9]\d{{4}}[A-Z]{{0,3}}|1[0-9]\d{{4}}[A-Z]{{0,3}})\s+(.+)$")
CODE_ONLY_RE = re.compile(r"^\d{6}[A-Z]{0,3}$")
CLS_RE = re.compile(r"^(\d{4})\s+(\S+类)$")
# 目录注释："可授工学或理学学士学位"
NOTE_RE = re.compile(rf"可授({CAT_ALT})或({CAT_ALT})学士")


def clean_name(n: str) -> str:
    n = re.sub(r"（注：[^）]*）", "", n)
    n = re.sub(r"\([^)]*\)", "", n)
    return n.strip()


def parse_catalog() -> tuple[dict[str, list[str]], dict[str, str]]:
    """解析目录 → (专业名→[门类] 多归属, 类名→门类)。"""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(CATALOG_DOCX))
    state = {"cat": None}
    single: dict[str, str] = {}
    multi_notes: dict[str, list[str]] = {}
    class_map: dict[str, str] = {}

    def feed(code: str, name: str):
        m = re.search(r"学科门类[:：]\s*(\S+)", (name or "") + " " + (code or ""))
        if m:
            state["cat"] = re.sub(r"\d+$", "", m.group(1))
            return
        cat = state["cat"]
        if not cat:
            return
        cm = CLS_RE.match(f"{code} {name}")
        if cm:
            class_map[cm.group(2)] = cat
            return
        if CODE_ONLY_RE.match(code) and name:
            nm = clean_name(name)
            single[nm] = cat
            nm_note = NOTE_RE.search(name)
            if nm_note:
                multi_notes[nm] = [nm_note.group(1), nm_note.group(2)]
            return
        pm = PARA_CODE_RE.match(f"{code} {name}")
        if pm:
            nm = clean_name(pm.group(2))
            single[nm] = cat
            pm_note = NOTE_RE.search(pm.group(2))
            if pm_note:
                multi_notes[nm] = [pm_note.group(1), pm_note.group(2)]

    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            t = Paragraph(child, doc).text.strip()
            if not t:
                continue
            m = re.search(r"学科门类[:：]\s*(\S+)", t)
            if m:
                state["cat"] = re.sub(r"\d+$", "", m.group(1))
                continue
            parts = t.split(None, 1)
            if len(parts) == 2:
                feed(parts[0], parts[1])
        elif child.tag.endswith("}tbl"):
            tbl = Table(child, doc)
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells]
                if len(cells) >= 2 and cells[0]:
                    feed(cells[0], cells[1])

    mapping: dict[str, list[str]] = {}
    for name, c in single.items():
        extra = multi_notes.get(name) or []
        cats = sorted({*(extra if all(x in CATEGORIES for x in extra) else []), c})
        mapping[name] = cats or [c]
    return mapping, class_map


def classify(name: str, mapping: dict[str, list[str]], class_map: dict[str, str]) -> list[str]:
    n = (name or "").strip()
    if not n:
        return [OTHER]
    if n in mapping:
        return mapping[n]
    stripped = re.sub(r"[（(][^（）()]*[）)]", "", n).strip()
    if stripped != n and stripped in mapping:
        return mapping[stripped]
    cands = [(k, v) for k, v in mapping.items() if len(k) >= 3 and k in n]
    if cands:
        cands.sort(key=lambda kv: -len(kv[0]))
        return cands[0][1]
    if stripped.endswith("类") and stripped in class_map:
        return [class_map[stripped]]
    cands = [(k, v) for k, v in class_map.items() if len(k) >= 3 and k[:-1] in n]
    if cands:
        cands.sort(key=lambda kv: -len(kv[0]))
        return [cands[0][1]]
    return [OTHER]


def program_type_of(name: str) -> str:
    if "中外合作" in name or "合作办学" in name:
        return "中外合作"
    if "试验班" in name or "实验班" in name:
        return "试验班"
    return "normal"


def classify_trial(name: str, mapping, class_map) -> list[str]:
    """试验班 → 门类（多归属），关键词不中再走普通匹配。"""
    for pat, cats in TRIAL_RULES:
        if re.search(pat, name):
            return cats
    return classify(name, mapping, class_map)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not CATALOG_DOCX.exists():
        print(f"目录文件不存在: {CATALOG_DOCX}")
        return 1
    mapping, class_map = parse_catalog()
    print(f"目录解析: {len(mapping)} 专业 / {len(class_map)} 专业类")
    assert all(c in CATEGORIES + [OTHER] for v in mapping.values() for c in v), "门类出现脏值"

    conn = sqlite3.connect(get_custom_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT college_id, major_id, major_name FROM college_major_name "
        "WHERE major_name IS NOT NULL AND TRIM(major_name)!=''"
    ).fetchall()
    print(f"待归类专业行: {len(rows)}")

    pt_counter: Counter[str] = Counter()
    cat_counter: Counter[str] = Counter()
    updates = []
    for r in rows:
        name = r["major_name"]
        pt = program_type_of(name)
        if pt == "试验班":
            cats = classify_trial(name, mapping, class_map)
        else:
            cats = classify(name, mapping, class_map)
        pt_counter[pt] += 1
        for c in cats:
            cat_counter[c] += 1
        updates.append((r["college_id"], r["major_id"], pt, cats))

    print("\nprogram_type 分布:", dict(pt_counter))
    print("category 归属计数:", dict(sorted(cat_counter.items(), key=lambda x: -x[1])))
    other = cat_counter.get(OTHER, 0)
    total_assign = sum(cat_counter.values())
    print(f"未匹配率(其他/总归属): {other}/{total_assign} = {other / total_assign * 100:.1f}%")

    if not args.dry_run:
        conn.execute("DELETE FROM college_major_category")
        for cid, mid, pt, cats in updates:
            conn.execute(
                "UPDATE college_major_name SET program_type=? WHERE college_id=? AND major_id=?",
                (pt, cid, mid),
            )
            for c in cats:
                conn.execute(
                    "INSERT OR IGNORE INTO college_major_category (college_id, major_id, category) VALUES (?,?,?)",
                    (cid, mid, c),
                )
        conn.commit()
        print(f"已写入 {len(updates)} 行 program_type + 关联表归属")
    else:
        print("(--dry-run 未写入)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
