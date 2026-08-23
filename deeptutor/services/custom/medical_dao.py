from __future__ import annotations

import re

from deeptutor.services.custom.db import get_connection


# 志愿册专业备注 → 体检受限码 硬限制规则（学校明确不招收）
HARD_NOTE_RULES: list[tuple[str, frozenset[str]]] = [
    (r"不招色盲色弱", frozenset({"101", "102"})),
    (r"不招色盲", frozenset({"102"})),
    (r"不招色弱", frozenset({"101"})),
    (r"不招单色识别不全", frozenset({"103"})),
    (r"单色识别不全者不予录取", frozenset({"103"})),
    (r"裸眼视力不低于?\s*4\.8|裸眼视力[≥≥]\s*4\.8", frozenset({"202"})),
    (r"裸眼视力不低于?\s*5\.0|裸眼视力[≥≥]\s*5\.0", frozenset({"201"})),
]

# 软提醒规则（"不宜就读"/"慎重报考"句式，标注但不剔除）
SOFT_NOTE_RULES: list[tuple[str, frozenset[str]]] = [
    (r"色盲色弱", frozenset({"101", "102"})),
    (r"色盲", frozenset({"102"})),
    (r"色弱", frozenset({"101"})),
    (r"单色识别不全", frozenset({"103"})),
    (r"转氨酶", frozenset({"405"})),
]

_MEDICAL_KEYWORD = re.compile(
    r"色弱|色盲|单色识别|色觉|视力|裸眼|矫正|听力|听觉|嗅觉|口吃|斜视|转氨酶|肢体残疾|体检|"
    r"糖尿病|癫痫|心脏病|传染病|慢性病|肝功能"
)
_MEDICAL_DROP = re.compile(r"政审|面试|户籍|就业|加试|定向|男生|女生")
_REQUIREMENT_KEYWORD = re.compile(r"政审|面试|只招|男生|女生|培养|年龄|考核|体测|体能|语种|签约|协议|服务|户籍|定向|招飞|学员|须|英语|俄语|日语|数学|成绩|不低于|第一志愿|时段")


def extract_requirement(note: str) -> str:
    """从备注中提取非医学报考要求（性别/政审面试/培养方向/年龄等），无则返回空串。

    与 extract_medical_clause 互补：医学限制入 medical_note（红字），
    其余报考要求入 requirement（琥珀提示）。
    """
    if not note:
        return ""
    units = re.findall(r"[（(]([^）)]*)[）)]|[^（(）)]+", note)
    kept: list[str] = []
    for u in units:
        u = u.strip()
        if not u:
            continue
        if _MEDICAL_KEYWORD.search(u):
            # 含医学关键词的单元拆分，只保留非医学要求子句
            for sub in re.split(r"[；;，,]", u):
                sub = sub.strip()
                if not sub or _MEDICAL_KEYWORD.search(sub):
                    continue
                if _REQUIREMENT_KEYWORD.search(sub):
                    kept.append(sub)
        elif _REQUIREMENT_KEYWORD.search(u):
            # 纯要求单元：保留（去校区/学制等）
            if re.search(r"校区|校本部|学制|学费|住宿费|主校区|新校区", u):
                continue
            kept.append(u)
    return "；".join(dict.fromkeys(kept))


def _trim_unit(u: str) -> str:
    """裁剪单元内医学关键词之前的说明性前缀（保留短衔接词）。"""
    m = _MEDICAL_KEYWORD.search(u)
    if not m or m.start() == 0:
        return u
    pre = u[: m.start()]
    if len(pre) <= 6:
        return u
    cut = max(pre.rfind("，"), pre.rfind("："), pre.rfind("。"), pre.rfind("；"))
    return u[cut + 1 :] if cut >= 0 else u[m.start() :]


def extract_medical_clause(note: str) -> str:
    """从备注中提取医学限制片段（去校区/户籍/政审/面试等无关内容），无限制则返回空串。"""
    if not note:
        return ""
    units = re.findall(r"[（(]([^）)]*)[）)]|[^（(）)]+", note)
    kept: list[str] = []
    for u in units:
        u = u.strip()
        if not u:
            continue
        if _MEDICAL_DROP.search(u) and _MEDICAL_KEYWORD.search(u):
            # 混合单元（如 政审+裸眼视力）：按标点拆分，只保留医学子句
            for sub in re.split(r"[；;，,]", u):
                sub = sub.strip()
                if not sub:
                    continue
                if _MEDICAL_DROP.search(sub) or not _MEDICAL_KEYWORD.search(sub):
                    continue
                kept.append(_trim_unit(sub))
        elif _MEDICAL_KEYWORD.search(u) and not _MEDICAL_DROP.search(u):
            kept.append(_trim_unit(u))
    return "；".join(dict.fromkeys(kept)).replace("，", "；").replace("、", "；")


def classify_medical_note(note: str) -> dict[str, set[str]]:
    """返回 {hard: set[codes], soft: set[codes]}。"""
    hard: set[str] = set()
    soft: set[str] = set()
    if not note:
        return {"hard": hard, "soft": soft}
    is_soft = ("慎重报考" in note) or ("不宜就读" in note) or ("不宜报读" in note)
    for pattern, codes in HARD_NOTE_RULES:
        if re.search(pattern, note):
            hard |= set(codes)
    for pattern, codes in SOFT_NOTE_RULES:
        if re.search(pattern, note):
            soft |= set(codes)
    if is_soft:
        hard = set()
    return {"hard": hard, "soft": soft}


def major_medical_status(note: str, user_codes: list[str] | None) -> str:
    """按用户勾选的受限项判断专业是否应剔除。

    - 'exclude'：专业备注为硬限制且命中用户勾选码
    - 'ok'：其余情况（含软提醒，仅前端红字展示）
    """
    if not user_codes:
        return "ok"
    user = set(user_codes)
    if not user:
        return "ok"
    cls = classify_medical_note(note)
    if cls["hard"] & user:
        return "exclude"
    return "ok"


def init_medical_tables() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS medical_restrictions (
            code TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            severity TEXT DEFAULT 'medium'
        );
        CREATE TABLE IF NOT EXISTS major_medical_restrictions (
            major_id TEXT NOT NULL,
            restriction_code TEXT NOT NULL REFERENCES medical_restrictions(code),
            PRIMARY KEY (major_id, restriction_code)
        );
    """)
    conn.commit()
    conn.close()


def seed_default_restrictions() -> None:
    from deeptutor.services.custom.student_profile import MEDICAL_RESTRICTION_MAP, RESTRICTION_AFFECTED_MAJORS
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM medical_restrictions").fetchone()[0]
    if existing > 0:
        conn.close()
        return
    cur = conn.cursor()
    for code, desc in MEDICAL_RESTRICTION_MAP.items():
        cur.execute(
            "INSERT OR IGNORE INTO medical_restrictions (code, description, severity) VALUES (?, ?, ?)",
            (code, desc, "high" if code.startswith("4") else "medium"),
        )
    for code, major_ids in RESTRICTION_AFFECTED_MAJORS.items():
        for mid in major_ids:
            cur.execute(
                "INSERT OR IGNORE INTO major_medical_restrictions (major_id, restriction_code) VALUES (?, ?)",
                (mid, code),
            )
    conn.commit()
    conn.close()


def get_restrictions_by_major(major_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.code, r.description
        FROM medical_restrictions r
        JOIN major_medical_restrictions m ON r.code = m.restriction_code
        WHERE m.major_id = ?
    """, (major_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_restrictions() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT code, description, severity FROM medical_restrictions ORDER BY code").fetchall()
    conn.close()
    return [dict(r) for r in rows]
