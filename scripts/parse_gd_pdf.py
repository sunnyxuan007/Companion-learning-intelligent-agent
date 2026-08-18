#!/usr/bin/env python3
"""Parse Guangdong 2026 admission major catalog PDF into structured JSON.

The PDF is a multi-column catalog (2-3 schools per page, some schools span
multiple pages). Strategy:
  1. Per page, find college header rows (5-digit code + name).
  2. Assign every cell to the college whose x-region it falls into.
  3. Within a college, parse group headers and major records.
  4. Merge records across pages by college_id.

Usage:
    python parse_gd_pdf.py --pdf PATH --db PATH --out PATH
"""
import argparse
import json
import re
import sqlite3
from collections import defaultdict

import pdfplumber

MAJOR_RE = re.compile(r"^(\d{3})$")
MAJOR_PLAN_RE = re.compile(r"^(\d{3})\s*([^\d]+?)\s*(\d+)$")
NAME_PLAN_RE = re.compile(r"^([^\d]+?)\s*(\d+)$")
GROUP_RE = re.compile(r"^专业组(\d+)$")
COLLEGE_RE = re.compile(r"^(\d{5})$")

BAN = ("再选", "学费", "办学地点", "以上专业", "专业除", "学制", "住宿费",
       "特征要求", "外语语种", "成绩要求", "前两年", "后两年", "与澳", "联合培养",
       "项目", "请查看", "本文件", "安托生涯", "验证答案", "学习费用", "培养模式",
       "年须向", "查看学校", "学校网站", "教育部卓越", "含材料", "含土木", "含能源",
       "含机械", "双学士学", "位复合型", "国际班", "卓越", "创新实验班",
       "普通类", "招生专业", "目录", "—", "页", "本文件")

EXCLUDE_TOKENS = (
    "学费", "学年", "住宿费", "办学地点", "再选", "以上专业", "专业除",
    "学制", "特征要求", "外语语种", "成绩要求", "本文件", "安托生涯",
    "普通类", "招生专业", "目录", "—", "定向", "专项", "少数民族",
    "预科", "验证答案", "学习费用", "培养", "前两年", "后两年",
)


def clean(t):
    return not any(b in t for b in BAN)


def get_college_map(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    m = {}
    for r in conn.execute(
        "SELECT official_code, province_code FROM college_code_map WHERE province='广东'"
    ).fetchall():
        m.setdefault(r[1], r[0])
    conn.close()
    return m


def rows_by_top(words, tol=3):
    rows = defaultdict(list)
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        placed = False
        for k in rows:
            if abs(k - w["top"]) <= tol:
                rows[k].append(w)
                placed = True
                break
        if not placed:
            rows[round(w["top"])].append(w)
    return [sorted(v, key=lambda x: x["x0"]) for _, v in sorted(rows.items())]


def split_cells(row_words, gap=25):
    if not row_words:
        return []
    cells = []
    cur = [row_words[0]]
    for w in row_words[1:]:
        if w["x0"] - cur[-1]["x0"] > gap:
            cells.append(cur)
            cur = [w]
        else:
            cur.append(w)
    cells.append(cur)
    return cells


def parse_page(page, college_map):
    words = page.extract_words()
    # Skip index/TOC pages: no "专业组" anywhere on the page
    full_text = "".join(w["text"] for w in words)
    if "专业组" not in full_text:
        return [], []
    rows = rows_by_top(words)
    headers = []
    for row in rows:
        code = None
        name = ""
        x0 = None
        for w in row:
            m = COLLEGE_RE.match(w["text"])
            if m:
                code = m.group(1)
                x0 = w["x0"]
                break
        if code:
            tail = [w for w in row if w["x0"] > x0 and COLLEGE_RE.match(w["text"]) is None
                    and not w["text"].isdigit()]
            if tail:
                name = tail[0]["text"]
                m = re.match(r"^(.+?)(\d{1,4})$", name)
                if m and any('\u4e00' <= c <= '\u9fff' for c in m.group(1)):
                    name = m.group(1)
            headers.append((x0, code, name, college_map.get(code, code)))
    headers.sort(key=lambda h: h[0])
    if not headers:
        return [], []

    def college_for_x(x0):
        best = None
        best_d = 1e9
        hits = []
        for hx, code, name, official in headers:
            lo, hi = hx - 30, hx + 220
            if lo <= x0 <= hi:
                hits.append((abs(x0 - hx), official))
            d = abs(x0 - hx)
            if d < best_d:
                best_d = d
                best = official
        if hits:
            # if multiple regions overlap, pick the closest header x
            hits.sort(key=lambda p: p[0])
            return hits[0][1]
        return best

    state = {}
    for hx, code, name, official in headers:
        state[official] = {
            "rec": {"college_id": official, "college_code": code,
                    "name": name, "groups": []},
            "cur_group": None,
            "last_major": None,
        }

    for row in rows:
        row_code = None
        for w in row:
            m = COLLEGE_RE.match(w["text"])
            if m:
                row_code = m.group(1)
                break
        if row_code:
            continue
        cells = split_cells(row)
        for cell in cells:
            texts = [w["text"] for w in cell]
            x0 = cell[0]["x0"]
            official = college_for_x(x0)
            st = state[official]
            cur_college = st["rec"]
            cur_group = st["cur_group"]
            last_major = st["last_major"]
            gmatch = None
            for t in texts:
                g = GROUP_RE.match(t)
                if g:
                    gmatch = g
                    break
            if gmatch:
                cur_group = {"group_code": gmatch.group(1), "majors": []}
                cur_college["groups"].append(cur_group)
                st["cur_group"] = cur_group
                st["last_major"] = None
                continue
            if cur_group is None:
                continue
            if len(texts) == 1 and not clean(texts[0]) and not texts[0].isdigit():
                continue
            major_id = None
            name_parts = []
            plan = None
            for t in texts:
                comb = MAJOR_PLAN_RE.match(t)
                if comb:
                    major_id = comb.group(1)
                    name_parts.append(comb.group(2))
                    plan = comb.group(3)
                    continue
                mm = MAJOR_RE.match(t)
                if mm and major_id is None:
                    major_id = mm.group(1)
                    continue
                if mm and major_id is not None:
                    plan = mm.group(1)
                    continue
                if t.isdigit():
                    if major_id is not None and plan is None:
                        plan = t
                    continue
                npr = NAME_PLAN_RE.match(t)
                if npr and major_id is not None and plan is None:
                    name_parts.append(npr.group(1))
                    plan = npr.group(2)
                    continue
                if clean(t):
                    name_parts.append(t)
            if major_id and name_parts:
                name = "".join(name_parts)
                majors = cur_group["majors"]
                majors.append({"major_id": major_id, "name": name,
                               "plan": int(plan) if plan else None})
                st["last_major"] = majors[-1]
            elif len(texts) == 1 and texts[0].isdigit() and last_major and last_major["plan"] is None:
                last_major["plan"] = int(texts[0])
    return [st["rec"] for st in state.values()], []


def merge_records(records):
    """Merge per-page records of same college across pages."""
    merged = {}
    for rec in records:
        cid = rec["college_id"]
        if cid not in merged:
            merged[cid] = {"college_id": cid, "college_code": rec["college_code"],
                           "name": rec["name"], "groups": []}
        mrec = merged[cid]
        if not mrec["name"] and rec["name"]:
            mrec["name"] = rec["name"]
        for g in rec["groups"]:
            gcode = g["group_code"]
            existing = next((x for x in mrec["groups"] if x["group_code"] == gcode), None)
            if existing is None:
                mrec["groups"].append(g)
            else:
                seen = {m["major_id"] for m in existing["majors"]}
                for m in g["majors"]:
                    if m["major_id"] not in seen:
                        existing["majors"].append(m)
                        seen.add(m["major_id"])
    return list(merged.values())


def parse_pdf(pdf_path, college_map, progress_cb=None):
    all_records = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            recs, _ = parse_page(page, college_map)
            all_records.extend(recs)
            if progress_cb and (i + 1) % 25 == 0:
                progress_cb(i + 1, total)
    return merge_records(all_records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--db", default="data/user/custom/deeptutor_custom.db")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cmap = get_college_map(args.db)

    def prog(done, total):
        print(f"  progress {done}/{total}", flush=True)

    records = parse_pdf(args.pdf, cmap, prog)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"records": records}, f, ensure_ascii=False, indent=1)
    n_groups = sum(len(r["groups"]) for r in records)
    n_majors = sum(len(g["majors"]) for r in records for g in r["groups"])
    print(f"完成: {len(records)} 院校, {n_groups} 专业组, {n_majors} 专业")
    print(f"输出: {args.out}")


if __name__ == "__main__":
    main()