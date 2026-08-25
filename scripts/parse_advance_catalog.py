"""解析 2026 招生专业目录提前批段落 → 组内专业明细 + 限制要求入库。

口径（AGENTS.md Phase 23.2）：2026 报考 → 招生计划（专业明细）用 2026 目录，
排位用 2025 投档表。本脚本只写专业明细（year=2026、min_rank=0、rank_source='catalog'）。

来源：2026年广东省高考物理类/历史类招生专业目录.pdf（文本层，提前批详情页）
匹配：官方 2025 投档表 GEN 组（(college_id, group_code) 已存在才写）
major_id 命名空间：{group_code}-{专业代码}（避免与本科批同码专业在 college_major_name PK 冲突）
写入：admission_ranks 专业行 + college_major_name（名称/再选/学制/学费/校区/体检限制/特征要求）

用法：python scripts/parse_advance_catalog.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber  # noqa: E402

from deeptutor.services.custom.db import get_custom_db_path  # noqa: E402
from deeptutor.services.custom.medical_dao import extract_medical_clause  # noqa: E402

DATA_DIR = Path.home() / "桌面/data for agent"
PHYSICS_PDF = DATA_DIR / "2026年广东省高考物理类招生专业目录.pdf"
HISTORY_PDF = DATA_DIR / "2026年广东省高考历史类招生专业目录.pdf"

BATCH_MARKERS = [
    ("军检、面试院校", "提前批本科-军检类"),
    ("空军、海军招飞", "提前批本科-空军海军招飞"),
    ("非军检、面试院校", "提前批本科-非军检类"),
    ("教师专项", "提前批本科-教师专项"),
    ("农村卫生专项", "提前批本科-卫生专项"),
    ("特殊类型招生", "提前批本科-特殊类型招生"),
    ("定向培养军士", "提前批专科-定向军士"),
]

GROUP_RE = re.compile(r"^专业组(\d+)$")
COLLEGE_RE = re.compile(r"^(\d{5})$")
MAJOR_RE = re.compile(r"^(\d{3})$")
MAJOR_PLAN_RE = re.compile(r"^(\d{3})\s*([^\d]+?)\s*(\d+)$")
NAME_PLAN_RE = re.compile(r"^([^\d]+?)\s*(\d+)$")
ZAILXUAN_RE = re.compile(r"^再选[:：；;]\s*(.+)$")

TAIL_KW = re.compile(
    r"学制|学费|住宿费|外语语种|特征要求|成绩要求|办学地点|以上专业|培养|政审|面试|体检|"
    r"只招|不招|矫正|裸眼|心理|服从|志愿|预科|本研|衔接|新生|第一年|学年"
)

BAN_WORDS = (
    "安托生涯", "验证答案", "本文件", "普通类", "招生专业", "目录", "页", "—", "QQ",
)


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


def detect_batch(text: str) -> str | None:
    j = re.sub(r"\s+", "", text)
    j = j.replace(".", "·").replace(",", "·").replace("，", "·")
    if "提前批·专科" in j:
        return "提前批专科-定向军士"
    # 特殊类型页标题形如「提前批·特殊类型招生·高水平运动队」，不含「提前批·本科」
    if "特殊类型招生" in j and "专业组" in j:
        return "提前批本科-特殊类型招生"
    if "提前批·本科" not in j:
        return None
    for marker, batch in BATCH_MARKERS:
        if marker in j:
            return batch
    return None


def parse_page_words(page, college_map):
    words = page.extract_words()
    full = "".join(w["text"] for w in words)
    if "专业组" not in full:
        return {}
    rows = rows_by_top(words)
    headers = []
    for row in rows:
        code = None
        x0 = None
        for w in row:
            m = COLLEGE_RE.match(w["text"])
            if m:
                code = m.group(1)
                x0 = w["x0"]
                break
        if code:
            tail = [w for w in row if w["x0"] > x0 and COLLEGE_RE.match(w["text"]) is None and not w["text"].isdigit()]
            name = ""
            if tail:
                name = tail[0]["text"]
                m = re.match(r"^(.+?)(\d{1,4})$", name)
                if m and any('\u4e00' <= c <= '\u9fff' for c in m.group(1)):
                    name = m.group(1)
            headers.append((x0, code, name))
    headers.sort(key=lambda h: h[0])
    if not headers:
        return {}

    def college_for_x(x0):
        best, best_d = None, 1e9
        for hx, code, _name in headers:
            d = abs(x0 - hx)
            if d < best_d:
                best_d, best = d, code
        return best

    recs: dict[str, dict] = {}
    for hx, code, name in headers:
        recs[code] = {"college_id": college_map.get(code, code), "code": code,
                      "name": name, "groups": [], "cur_group": None,
                      "last_major": None, "tail_on": False}

    for row in rows:
        row_code = None
        for w in row:
            m = COLLEGE_RE.match(w["text"])
            if m:
                row_code = m.group(1)
                break
        if row_code:
            for code in recs:
                recs[code]["tail_on"] = False
            continue
        cells = split_cells(row)
        for cell in cells:
            texts = [w["text"] for w in cell]
            x0 = cell[0]["x0"]
            code = college_for_x(x0)
            if code not in recs:
                continue
            st = recs[code]
            cur_group = st["cur_group"]
            last_major = st["last_major"]
            joined = "".join(texts)

            if any(any(b in t for t in texts) for b in BAN_WORDS):
                continue
            gmatch = next((GROUP_RE.match(t) for t in texts if GROUP_RE.match(t)), None)
            if gmatch:
                cur_group = {"group_code": gmatch.group(1), "majors": [],
                             "subject_requirement": "", "req_parts": []}
                st["groups"].append(cur_group)
                st["cur_group"] = cur_group
                st["last_major"] = None
                st["tail_on"] = False
                continue
            if cur_group is None:
                continue
            zm = ZAILXUAN_RE.match(joined.strip())
            if zm:
                cur_group["subject_requirement"] = zm.group(1).strip()
                continue
            # 尾部限制块（学制/学费/特征要求/培养说明等）
            if TAIL_KW.search(joined):
                cur_group["req_parts"].append(joined)
                st["tail_on"] = True
                continue
            # 专业行
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
                if any('\u4e00' <= c <= '\u9fff' for c in t):
                    name_parts.append(t)
            if major_id and name_parts:
                name = "".join(name_parts)
                majors = cur_group["majors"]
                majors.append({"major_id": major_id, "name": name,
                               "plan": int(plan) if plan else None})
                st["last_major"] = majors[-1]
                st["tail_on"] = False
            elif len(texts) == 1 and texts[0].isdigit() and last_major and last_major["plan"] is None:
                last_major["plan"] = int(texts[0])
            elif last_major and not TAIL_KW.search(joined) and joined.strip() and not joined.isdigit() \
                    and any(c in joined for c in "()（）"):
                # 专业名换行续段（如 '挥)' 接 '飞行技术(航空飞行与指'）
                last_major["name"] = last_major["name"] + joined.strip()
            elif st["tail_on"] and joined.strip():
                # 尾部续行（培养说明等多行文本）
                cur_group["req_parts"].append(joined)
    return recs


def parse_tail(req_text: str) -> dict:
    req = re.sub(r"\s+", " ", req_text).strip()
    years = ""
    m = re.search(r"学制[:：]\s*(\d+)年", req)
    if m:
        years = m.group(1)
    tuition = 0.0
    if "免费" in req.split("学费")[-1][:12] if "学费" in req else False:
        tuition = 0.0
    else:
        m2 = re.search(r"学费[:：]\s*(\d+(?:\.\d+)?)", req)
        if m2:
            tuition = float(m2.group(1))
    campus = ""
    m3 = re.search(r"办学地点[:：]\s*([^；;]+)", req)
    if m3:
        campus = m3.group(1).strip()
    medical_note = extract_medical_clause(req)
    # requirement = 去掉学制/学费/住宿费/办学地点/再选片段后的限制说明
    rest = re.sub(r"(学制|学费|住宿费|办学地点|外语语种|成绩要求)[:：][^；;]*[；;]?", " ", req)
    rest = re.sub(r"\s+", " ", rest).strip(" ；;")
    return {"years": years, "tuition": tuition, "campus": campus,
            "medical_note": medical_note, "requirement": rest}


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
    # 官方 2025 投档 GEN 组：batch 以此为准，且只写有 2025 位次的组
    gen_groups: dict[tuple[str, str], tuple[str, str]] = {}
    for r in conn.execute(
        """SELECT college_id, group_code, batch, exam_category FROM admission_ranks
           WHERE province='广东' AND year=2025 AND major_id='GEN' AND min_rank > 0
             AND batch LIKE '提前批本科%'"""
    ).fetchall():
        gen_groups[(r["college_id"], r["group_code"])] = (r["batch"], r["exam_category"])

    total_majors = 0
    total_groups = 0
    unmatched_groups = 0
    skipped_zhuan = 0

    for pdf_path, exam_category in ((PHYSICS_PDF, "物理"), (HISTORY_PDF, "历史")):
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                full = page.extract_text() or ""
                batch = detect_batch(full)
                if batch is None:
                    continue
                if batch.startswith("提前批专科"):
                    skipped_zhuan += 1
                    continue
                recs = parse_page_words(page, code_map)
                for code, st in recs.items():
                    cid = st["college_id"]
                    for g in st["groups"]:
                        key = (cid, g["group_code"])
                        if key not in gen_groups:
                            unmatched_groups += 1
                            continue
                        b_batch, b_cat = gen_groups[key]
                        tail = parse_tail(" ".join(g["req_parts"]))
                        total_groups += 1
                        for m in g["majors"]:
                            ns_mid = f"{g['group_code']}-{m['major_id']}"
                            total_majors += 1
                            if not args.dry_run:
                                conn.execute(
                                    """INSERT OR IGNORE INTO admission_ranks
                                       (college_id, major_id, province, year, batch, min_rank, min_score,
                                        enrollment_count, exam_category, group_code, rank_source, art_category)
                                       VALUES (?, ?, '广东', 2026, ?, 0, 0.0, ?, ?, ?, 'catalog', '')""",
                                    (cid, ns_mid, b_batch, m.get("plan") or 0, b_cat, g["group_code"]),
                                )
                                conn.execute(
                                    """INSERT OR IGNORE INTO college_major_name
                                       (college_id, major_id, major_name, full_name, category,
                                        subject_requirement, tuition, years, campus, medical_note, requirement)
                                       VALUES (?, ?, ?, '', '', ?, ?, ?, ?, ?, ?)""",
                                    (cid, ns_mid, m["name"], g.get("subject_requirement", ""),
                                     tail["tuition"], tail["years"], tail["campus"],
                                     tail["medical_note"], tail["requirement"]),
                                )
        print(f"{exam_category} 目录处理完成")

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\n提前批组明细写入: {total_groups} 组 / {total_majors} 专业行")
    print(f"未匹配 2025 投档组: {unmatched_groups} | 专科提前跳过页: {skipped_zhuan}")
    if args.dry_run:
        print("(--dry-run 未写入)")
    return 0


if __name__ == "__main__":
    sys.exit(main())