#!/usr/bin/env python3
"""解析 2026 广东省招生专业目录（体育艺术版）DOCX → 每专业组内的专业明细。

数据源：用户提供的 `（已压缩）2026年广东省招生专业目录 体育艺术版.docx`（16.6MB document.xml）。
目标：为已导入 admission_ranks 的艺体类本科批 1347 个组（GEN-only）补组内专业明细
（major_id / major_name / 计划数 / 学制 / 学费 / 办学地点）。

用法：
    python scripts/parse_art_catalog.py --docx PATH --out out.json   # 仅解析出 JSON
    python scripts/parse_art_catalog.py --docx PATH --write           # 直接写库
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 7 个本科·统考 明细段范围（段落索引，含起止，到 专科/提前批 段为止）
SECTIONS = [
    ("体育", "体育类·本科", 2109, 3055),
    ("音乐", "音乐类·本科·统考", 4359, 6611),
    ("舞蹈", "舞蹈类·本科·统考", 7198, 7912),
    ("美术", "美术与设计类·本科·统考", 8475, 11758),
    ("书法", "书法类·本科·统考", 12658, 12828),
    ("播音", "播音与主持类·本科·统考", 12921, 13455),
    ("表导", "表(导)演类·本科·统考", 13623, 14166),
]

COLLEGE_RE = re.compile(r"^(\d{5})\s+([\u4e00-\u9fffA-Za-z][^\d]*?)")
# 行内嵌院校头：5 位码 + 空格 + 中文名（出现在注释文本末尾，如 `...校本部  10112   太原理工大学`）
EMBED_COLLEGE_RE = re.compile(r"(?<![\d])(\d{5})\s+([\u4e00-\u9fff][^\d]*?)(?=\s+\d+\.?\d*\s*$|\s*$|\s+\d{1,3}\s+专业组|\s+专业组)")
GROUP_RE = re.compile(r"^专业组(\d{1,3})")
# 专业行：`012  产品设计 10`、`016 体育教育 11 学制：4年；...`、可多个同行
# 每格：3位码 + 名称（可含空格/括号）+ 计划数(可选)
MAJOR_CELL_RE = re.compile(
    r"(?<![\d])(\d{3})\s+([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z()（）【】、+·/&\-– ]*?)\s*(?=\d{1,3}\s*(?:$|\s)|\s*$|\s+工(?:\s|$)|\s+(?:\(|以上专业|学制|学费|办学地点|特征要求|成绩要求|住宿费|专业省统考|不招|仅招|请|根据|备注|与|含|不含|年|弱|录取|收费标准|第一年|创新|声乐|音|动|绘|美|数|影|视|美术))")
# 主题要求行
SUBJECT_RE = re.compile(r"^首选")

# 注释行/续行的起始关键词
NOTE_KEYWORDS = (
    "以上专业", "学制", "学费", "办学地点", "特征要求", "成绩要求", "住宿费",
    "专业省统考", "不招", "仅招", "请", "根据", "备注", "与英国", "与俄",
    "含", "不含", "音 乐", "声乐", "年；", "弱；", "收费标准", "第一年",
    "具体培养", "创新", "录取", "培养", "美术", "绘画", "动画", "数字媒体",
    "影视", "视觉传达", "艺术", "设计", "办学地点",
)

EXTRACT_RE = {
    "years": re.compile(r"学制[:：]\s*(\d+)年"),
    "tuition": re.compile(r"学费[:：]\s*(\d+)"),
    "campus": re.compile(r"办学地点[:：]\s*([^；;]+)"),
}


def extract_text_paras(docx_path: str) -> list[str]:
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    return [
        "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
        for p in paras
    ]


class GroupParser:
    """针对一个类别段的状态机解析器。"""

    def __init__(self, category: str):
        self.category = category
        self.colleges: list[dict] = []
        self.cur: dict | None = None
        self.cur_group: dict | None = None
        self.pending_major: dict | None = None
        self.pending_note: str = ""
        self.cur_year_plan: int | None = None  # 组头行尾的计划数（可选）
        self.note_mode: bool = False  # 当前累积的是注释（区别于专业名续行）

    def new_college(self, code: str, name: str):
        self.cur = {"college_id": code, "name": name.strip(), "groups": []}
        self.colleges.append(self.cur)
        self.cur_group = None
        self.pending_major = None
        self.pending_note = ""
        self.note_mode = False

    def new_group(self, code: str, plan: str | None = None):
        if self.cur is None:
            return
        g = {"code": code, "plan": int(plan) if plan else None, "majors": [],
             "note": ""}
        self.cur["groups"].append(g)
        self.cur_group = g
        self.pending_major = None
        self.pending_note = ""
        self.note_mode = False

    def flush_note(self):
        """把累积的注释文本应用到最后一个专业（或组）。"""
        if not self.pending_note:
            return
        note = " ".join(self.pending_note.split())
        self.pending_note = ""
        self.note_mode = False
        if self.cur_group is None:
            return
        if self.pending_major is not None:
            # 注释挂在最近的专业上（除非是 以上专业 全组注释）
            if note.startswith("以上专业"):
                self.cur_group["note"] = (self.cur_group["note"] + " " + note).strip()
                self._apply_group_note(note)
                return
            self.pending_major.setdefault("notes", []).append(note)
            self._apply_extracted(self.pending_major, note)
        else:
            self.cur_group["note"] = (self.cur_group["note"] + " " + note).strip()
            if note.startswith("以上专业"):
                self._apply_group_note(note)

    def _apply_group_note(self, note: str):
        """把 `以上专业...` 全组注释的 学制/学费/办学地点 应用到组内全部专业（缺省时）。"""
        if self.cur_group is None:
            return
        flat = re.sub(r"\s+", "", note)
        ex = {}
        m = EXTRACT_RE["years"].search(flat)
        if m:
            ex["years"] = m.group(1)
        m = EXTRACT_RE["tuition"].search(flat)
        if m:
            ex["tuition"] = int(m.group(1))
        m = EXTRACT_RE["campus"].search(flat)
        if m:
            ex["campus"] = re.sub(r"[\s|]+", "", m.group(1)).strip("；;")
        for major in self.cur_group["majors"]:
            for k, v in ex.items():
                major.setdefault(k, v)

    def _apply_extracted(self, major: dict, note: str):
        flat = re.sub(r"\s+", "", note)
        m = EXTRACT_RE["years"].search(flat)
        if m:
            major["years"] = m.group(1)
        m = EXTRACT_RE["tuition"].search(flat)
        if m:
            major["tuition"] = int(m.group(1))
        m = EXTRACT_RE["campus"].search(flat)
        if m:
            major["campus"] = re.sub(r"[\s|]+", "", m.group(1)).strip("；;")

    def process_line(self, raw: str):
        if not raw.strip():
            return
        # ---- 按内嵌院校头 + 内嵌组头切分 ----
        for seg in split_tokens(raw):
            if seg.startswith("专业组"):
                m = re.match(r"专业组(\d{1,3})\s*(\d{1,3}|工)?", seg)
                if m:
                    self.flush_note()
                    plan = m.group(2) if m.group(2) and m.group(2) != "工" else None
                    self.new_group(m.group(1), plan)
            elif re.match(r"^(\d{5})\s+[\u4e00-\u9fffA-Za-z]", seg):
                m = re.match(r"(\d{5})\s+([\u4e00-\u9fffA-Za-z][^\d]*)", seg)
                if m:
                    self.flush_note()
                    self.new_college(m.group(1), m.group(2))
            else:
                self.process_segment(seg)

    def process_segment(self, t: str):
        """处理一段（已去掉内嵌院校头）。"""
        if not t.strip():
            return
        # ---- 组头 ----
        m = GROUP_RE.match(t)
        if m:
            self.flush_note()
            rest = t[m.end():].strip()
            plan = None
            pm = re.match(r"(\d{1,3})(?:\s|$)", rest)
            if pm:
                plan = pm.group(1)
            self.new_group(m.group(1), plan)
            return
        # ---- 主题要求行（可能尾部带专业） ----
        if SUBJECT_RE.match(t):
            t = re.sub(r"^首选[^ ]*", "", t).strip()
            if not t:
                return
        # ---- 专业行 ----
        if MAJOR_CELL_RE.match(t):
            self.flush_note()
            self._parse_major_cells(t)
            return
        # ---- 注释行 / 续行 ----
        self._handle_note_or_cont(t)

    def _parse_major_cells(self, t: str):
        """解析一行中可能存在的多个专业格。"""
        pos = 0
        for m in MAJOR_CELL_RE.finditer(t):
            code, name = m.group(1), m.group(2)
            # 跳过不是从行首/紧跟空格开始的部分
            if m.start() > 0 and t[m.start() - 1] not in " \t":
                continue
            # 提取计划数（在名字后）
            end = m.end()
            plan = None
            pm = re.match(r"(\d{1,3})(?:\s|$)", t[end:])
            if pm:
                plan = pm.group(1)
                # 更新匹配结束位置（用于找行尾注释）
                end = end + pm.end()
            major = {"major_id": code, "major_name": re.sub(r"\s+", "", name),
                     "plan": int(plan) if plan else None}
            if self.cur_group is None:
                continue
            self.cur_group["majors"].append(major)
            self.pending_major = major
            # 行尾注释文本
            tail = t[end:].strip()
            if tail and not tail.startswith("("):
                # 内联注释（如 `请器种...`、`学制：4年；...`）
                self.pending_note = tail
                self.note_mode = True
            pos = m.end()
        # 若行尾是 `(学费：xxx元/学年)` 单独括号注释
        rest = t[pos:].strip()
        if rest.startswith("(") and "学费" in rest:
            self.pending_note = rest
            self.note_mode = True

    def _handle_note_or_cont(self, t: str):
        """处理注释续行或专业名续行。"""
        stripped = t.strip()
        if stripped.startswith("(") and "学费" in stripped:
            self.pending_note = (self.pending_note + " " + stripped).strip()
            self.note_mode = True
            return
        if self.note_mode or _is_note_start(stripped):
            # 注释续行
            self.pending_note = (self.pending_note + " " + stripped).strip()
            self.note_mode = True
            return
        if self.pending_major is not None:
            # 专业名续行（如 `制 作 ) 1`）
            self.pending_major["major_name"] = re.sub(r"\s+", "", self.pending_major["major_name"]) \
                + re.sub(r"\s+", "", stripped)
            # 续行可能带计划数
            pm = re.match(r"(\d{1,3})$", re.sub(r"\s", "", stripped))
            if pm and self.pending_major.get("plan") is None:
                self.pending_major["plan"] = int(pm.group(1))
        elif self.cur_group is not None:
            self.cur_group["note"] = (self.cur_group["note"] + " " + stripped).strip()


def _is_note_start(t: str) -> bool:
    return any(t.startswith(k) for k in NOTE_KEYWORDS)


def split_tokens(line: str) -> list[str]:
    """把一行按内嵌院校头 / 内嵌组头切分为多个片段。

    - 内嵌院校头：`...校本部  10112   太原理工大学`（5位码，白名单校验）
    - 内嵌组头：`...南校园  专业组253                2`（注释行尾续组头）
    返回片段列表，片段本身即院校头或组头或正文。
    """
    known = _KNOWN_CODES
    out: list[str] = []
    pos = 0
    for m in EMBED_COLLEGE_RE.finditer(line):
        if m.group(1) not in known:
            continue
        if m.start() > pos:
            out.append(line[pos:m.start()])
        out.append(m.group(0))
        pos = m.end()
    tail = line[pos:] if pos < len(line) else ""
    # 尾部再按内嵌组头切分
    if tail.strip():
        gpos = 0
        for gm in re.finditer(r"专业组(\d{1,3})", tail):
            if gm.start() > gpos:
                out.append(tail[gpos:gm.start()])
            out.append(tail[gm.start():])
            gpos = gm.end()
        if gpos < len(tail):
            out.append(tail[gpos:])
    return out or [line]


# 全局已知院校码集合（行首真实院校头），在 parse_docx 时填充
_KNOWN_CODES: set[str] = set()


def parse_docx(docx_path: str) -> dict:
    texts = extract_text_paras(docx_path)
    # 收集全部行首院校码（真实院校头）作为内嵌码白名单
    for t in texts:
        m = re.match(r"(\d{5})\s+[\u4e00-\u9fffA-Za-z]", t)
        if m:
            _KNOWN_CODES.add(m.group(1))
    result = {}
    for cat, _name, start, end in SECTIONS:
        p = GroupParser(cat)
        for i in range(start, min(end, len(texts))):
            raw = texts[i]
            if not raw:
                continue
            # 跳过每页重复的类别页眉（如 `体育类 ·本科`、`体 育 类 · 本 科`）
            if len(raw) <= 30 and re.match(r"^[\u4e00-\u9fff·\s]+类", raw):
                continue
            p.process_line(raw)
        # 收尾
        p.flush_note()
        result[cat] = p.colleges
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docx", required=True, help="体育艺术版 DOCX 路径")
    ap.add_argument("--out", help="输出 JSON 路径")
    ap.add_argument("--write", action="store_true", help="直接写库")
    args = ap.parse_args()

    result = parse_docx(args.docx)
    total_groups = sum(len(c["groups"]) for colleges in result.values() for c in colleges)
    total_majors = sum(len(mj["majors"]) for colleges in result.values() for c in colleges
                       for g in c["groups"] for mj in [g])
    print(f"解析完成: 7 类, 组总数={total_groups}, 专业总数={total_majors}")
    for cat, colleges in result.items():
        g = sum(len(c["groups"]) for c in colleges)
        m = sum(len(cg["majors"]) for c in colleges for cg in c["groups"])
        print(f"  {cat}: 院校{len(colleges)} 组{g} 专业{m}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
        print(f"已写出 {args.out}")

    if args.write:
        _write_db(result)
    return 0


CAT_DB = {
    "体育": "体育",
    "音乐": "音乐",
    "舞蹈": "舞蹈",
    "美术": "美术与设计",
    "书法": "书法",
    "播音": "播音与主持",
    "表导": "表（导）演",
}


def _write_db(result: dict) -> None:
    from deeptutor.services.custom.db import get_connection

    conn = get_connection()
    # 地方码 → 官方码
    cmap = {}
    for r in conn.execute(
        "SELECT province_code, official_code FROM college_code_map"
    ).fetchall():
        cmap.setdefault(r["province_code"], r["official_code"])
    n_rows = n_cmn = 0
    n_group_hit = 0
    for cat, colleges in result.items():
        db_cat = CAT_DB[cat]
        for c in colleges:
            cid = cmap.get(c["college_id"], c["college_id"])
            for g in c["groups"]:
                # 仅写入 DB 中已有该组 GEN 行的组（避免目录独有组产生孤儿行）
                has_gen = conn.execute(
                    """SELECT 1 FROM admission_ranks
                       WHERE college_id=? AND group_code=? AND exam_category='艺体类'
                         AND art_category=? AND major_id='GEN' AND year=2026 AND batch='艺体类本科批'""",
                    (cid, g["code"], db_cat),
                ).fetchone()
                if not has_gen:
                    continue
                n_group_hit += 1
                for major in g["majors"]:
                    years = major.get("years", "")
                    tuition = major.get("tuition")
                    campus = major.get("campus", "")
                    # 组内专业 local 码会与普通类同校 major_id 冲突，命名空间加组号前缀
                    ns_major_id = f"{g['code']}-{major['major_id']}"
                    conn.execute(
                        """INSERT OR REPLACE INTO college_major_name
                           (college_id, major_id, major_name, full_name, tuition, years, campus)
                           VALUES (?,?,?,?,?,?,?)""",
                        (cid, ns_major_id, major["major_name"],
                         f"{major['major_name']}({campus})" if campus else major["major_name"],
                         tuition or 0, years, campus),
                    )
                    n_cmn += 1
                    conn.execute(
                        """INSERT OR REPLACE INTO admission_ranks
                           (college_id, major_id, province, year, batch, min_rank, min_score,
                            enrollment_count, exam_category, group_code, art_category, rank_source)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (cid, ns_major_id, "广东", 2026, "艺体类本科批", 0, 0,
                         major["plan"] or 0, "艺体类", g["code"], db_cat, "official"),
                    )
                    n_rows += 1
    conn.commit()
    conn.close()
    print(f"写库完成: 命中组{n_group_hit}, admission_ranks +{n_rows}, college_major_name +{n_cmn}")


if __name__ == "__main__":
    raise SystemExit(main())