from __future__ import annotations

import json
import time
from typing import Any

from deeptutor.services.custom.db import get_connection

RIASEC_LABELS: dict[str, str] = {
    "R": "实际型 (Realistic)",
    "I": "研究型 (Investigative)",
    "A": "艺术型 (Artistic)",
    "S": "社会型 (Social)",
    "E": "企业型 (Enterprising)",
    "C": "常规型 (Conventional)",
}

RIASEC_DESCRIPTIONS: dict[str, str] = {
    "R": "你喜欢动手操作、机械制作、户外活动等具体工作",
    "I": "你喜欢思考、分析和研究，对科学探索感兴趣",
    "A": "你喜欢创造、表达自我，对艺术和文学感兴趣",
    "S": "你喜欢帮助他人、教导和服务社会",
    "E": "你喜欢领导、组织和商业经营活动",
    "C": "你喜欢按规则办事、处理数据和细节工作",
}

QUESTIONS: list[dict[str, Any]] = [
    {"code": "R", "text": "我喜欢动手制作或修理东西"},
    {"code": "I", "text": "我喜欢探索事物的原理和规律"},
    {"code": "A", "text": "我喜欢写作、绘画或音乐等创造性活动"},
    {"code": "S", "text": "我喜欢帮助别人解决问题"},
    {"code": "E", "text": "我喜欢领导和组织团队活动"},
    {"code": "C", "text": "我喜欢按明确的规则和流程做事"},
    {"code": "R", "text": "我对机械、电子或建筑感兴趣"},
    {"code": "I", "text": "我擅长数学和科学类科目"},
    {"code": "A", "text": "我经常有新的创意和想法"},
    {"code": "S", "text": "我善于倾听和理解他人"},
    {"code": "E", "text": "我有较强的说服和谈判能力"},
    {"code": "C", "text": "我喜欢整理数据和制作表格"},
]

# Subject → RIASEC mapping
SUBJECT_RIASEC: dict[str, str] = {
    "数学": "I",
    "物理": "R",
    "化学": "I",
    "生物": "I",
    "地理": "R",
    "语文": "A",
    "外语": "E",
    "历史": "A",
    "政治": "S",
}

# Major → RIASEC mapping
MAJOR_RIASEC: dict[str, str] = {
    "计算机科学与技术": "IRC",
    "软件工程": "IRC",
    "机械工程": "R",
    "电气工程": "R",
    "土木工程": "R",
    "临床医学": "IS",
    "护理学": "S",
    "药学": "I",
    "汉语言文学": "A",
    "新闻传播": "AE",
    "法学": "ES",
    "工商管理": "ES",
    "金融学": "EC",
    "会计学": "C",
    "教育学": "S",
    "心理学": "IS",
    "建筑学": "AR",
    "艺术设计": "A",
    "英语": "AE",
    "经济学": "EI",
}

DISCLAIMER = "提示：霍兰德职业兴趣测试仅供参考，不能替代专业职业测评。测试结果仅作为志愿填报的参考之一。"


def calculate_riasec(scores: dict[str, int]) -> dict[str, Any]:
    sorted_codes = sorted(scores.items(), key=lambda x: -x[1])
    top3 = "".join(c[0] for c in sorted_codes[:3])
    return {
        "scores": scores,
        "top3": top3,
        "top3_labels": [RIASEC_LABELS.get(c, c) for c in top3],
    }


def get_major_recommendations(top3: str) -> list[dict[str, str]]:
    matching: list[dict[str, str]] = []
    for major, codes in MAJOR_RIASEC.items():
        common = set(top3) & set(codes)
        if common:
            matching.append({"major": major, "match_count": len(common), "riasec_codes": codes})
    matching.sort(key=lambda x: -x["match_count"])
    return matching


def save_assessment(user_id: str, scores: dict[str, int]) -> dict[str, Any]:
    result = calculate_riasec(scores)
    conn = get_connection()
    row = conn.execute(
        "SELECT settings_json FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    settings = json.loads(row["settings_json"]) if row else {}
    settings["holland_assessment"] = {"scores": scores, "result": result}

    now = time.time()
    conn.execute(
        """INSERT INTO user_settings (user_id, settings_json, created_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               settings_json = excluded.settings_json,
               updated_at = excluded.updated_at""",
        (user_id, json.dumps(settings, ensure_ascii=False), now, now),
    )
    conn.commit()
    conn.close()
    return result


def get_assessment(user_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT settings_json FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    settings = json.loads(row["settings_json"])
    return settings.get("holland_assessment")
