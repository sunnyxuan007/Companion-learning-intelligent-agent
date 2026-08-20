"""艺体类填报框架（广东本科普通批）。

官方规则（2026 广东）：
- 艺体类不分物理/历史，按计划类别（音乐/美术/体育等）统一划线、一起投档
- 本科批艺体类：1 个平行志愿组，共 20 个院校专业组志愿；每组内 6 个专业志愿 + 1 个服从调剂
- 投档：分数优先、遵循志愿，按合成总分（含加分）排位；同分 7 项排序，艺体类比专业省统考
- 双上线：文化与专业省统考成绩须同时达省控线方可投档
- 不得兼报：本科批艺体类不得兼报普通类

综合分公式（术科满分 300，综合分满分 750）：
- 音乐/舞蹈/表（导）演/美术与设计/书法：总分 = 文化×50% + 术科×2.5×50%
- 播音与主持类：总分 = 文化×60% + 术科×2.5×40%
- 体育类：总分 = 文化×40% + 术科×2.5×60%
"""

from __future__ import annotations

from typing import Any

# exam_category 统一标识
EXAM_CATEGORY_ART = "艺体类"

# 本科批艺体类批次名（区别于普通类"本科批"）
BATCH_ART_UNDERGRAD = "艺体类本科批"

# 8 类计划类别
ART_CATEGORIES: list[dict[str, str]] = [
    {"code": "音乐", "name": "音乐类", "formula": "art"},
    {"code": "舞蹈", "name": "舞蹈类", "formula": "art"},
    {"code": "表（导）演", "name": "表（导）演类", "formula": "art"},
    {"code": "播音与主持", "name": "播音与主持类", "formula": "broadcast"},
    {"code": "美术与设计", "name": "美术与设计类", "formula": "art"},
    {"code": "书法", "name": "书法类", "formula": "art"},
    {"code": "戏曲", "name": "戏曲类（省际联考）", "formula": "art"},
    {"code": "体育", "name": "体育类", "formula": "sports"},
]

# 本科批艺体类志愿规则
ART_SPORTS_RULES: dict[str, Any] = {
    "本科批": {
        "groups": 20,          # 1 个平行志愿组，共 20 个院校专业组志愿
        "majors_per_group": 6,  # 每组内最多 6 个专业志愿
        "mode": "院校专业组",
        "ratio": [3, 4, 3],    # 6 冲 / 8 稳 / 6 保
    }
}

CULTURE_FULL = 750
MAJOR_FULL = 300

# 计划类别 → 专业名关键词（用于无 art_category 列时的专业行过滤）
ART_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "音乐": ["音乐", "作曲", "演唱", "声乐", "器乐", "钢琴"],
    "舞蹈": ["舞蹈", "编导"],
    "表（导）演": ["表演", "导演", "戏剧", "影视"],
    "播音与主持": ["播音", "主持"],
    "美术与设计": ["美术", "设计", "绘画", "视觉传达", "环境设计", "动画", "数字媒体"],
    "书法": ["书法"],
    "戏曲": ["戏曲", "京剧"],
    "体育": ["体育", "运动", "武术", "田径", "足球", "篮球", "排球"],
}


def art_keywords(category_code: str) -> list[str]:
    """类别 → 专业名关键词列表（无则空）。"""
    return ART_CATEGORY_KEYWORDS.get(category_code, [])


# 类别 → 方向细分（对应一分一段表方向码；无细分时方向=类别码）
ART_DIRECTIONS: dict[str, list[str]] = {
    "音乐": ["音乐教育类", "音乐教育(声乐主项)", "音乐教育(器乐主项)",
            "音乐表演(声乐)", "音乐表演(器乐)"],
    "表（导）演": ["表(导)演(戏剧影视表演)", "表(导)演(服装表演)", "表(导)演(戏剧影视导演)"],
    "播音与主持": ["播音与主持(普通话)", "播音与主持(粤语)"],
    "美术与设计": ["美术与设计"],
    "书法": ["书法"],
    "舞蹈": ["舞蹈"],
    "体育": ["体育"],
    "戏曲": ["戏曲"],
}


def art_directions(category_code: str) -> list[str]:
    """类别 → 可用方向列表（无方向细分时返回单元素列表）。"""
    return ART_DIRECTIONS.get(category_code, [category_code])


def default_art_direction(category_code: str) -> str:
    """类别 → 默认方向。"""
    dirs = art_directions(category_code)
    return dirs[0] if dirs else category_code


def is_art_sports(exam_category: str | None) -> bool:
    """是否为艺体类科类。"""
    return bool(exam_category) and exam_category == EXAM_CATEGORY_ART


def art_formula(category_code: str) -> str:
    """类别 → 综合分公式类型：art / broadcast / sports。"""
    for c in ART_CATEGORIES:
        if c["code"] == category_code:
            return c["formula"]
    return "art"


def calc_composite_score(
    category_code: str,
    culture_score: float | None,
    major_score: float | None,
    bonus_points: float = 0,
) -> dict[str, Any]:
    """计算综合分。

    返回：{score, culture, major, formula, errors[]}
    - 音乐/舞蹈/表导/美术/书法/戏曲: culture*0.5 + major*2.5*0.5
    - 播音与主持: culture*0.6 + major*2.5*0.4
    - 体育: culture*0.4 + major*2.5*0.6
    """
    errors: list[str] = []
    if culture_score is None or major_score is None:
        errors.append("文化与专业统考分数均需填写")
        return {
            "score": None, "culture": culture_score, "major": major_score,
            "formula": art_formula(category_code), "errors": errors,
        }
    if culture_score < 0 or culture_score > CULTURE_FULL:
        errors.append(f"文化分应在 0-{CULTURE_FULL} 之间")
    if major_score < 0 or major_score > MAJOR_FULL:
        errors.append(f"专业统考分应在 0-{MAJOR_FULL} 之间")

    culture = culture_score + bonus_points
    major = major_score
    formula = art_formula(category_code)
    if formula == "broadcast":
        score = culture * 0.6 + major * 2.5 * 0.4
    elif formula == "sports":
        score = culture * 0.4 + major * 2.5 * 0.6
    else:
        score = culture * 0.5 + major * 2.5 * 0.5

    return {
        "score": round(score, 1),
        "culture": round(culture, 1),
        "major": major,
        "formula": formula,
        "errors": errors,
    }


def art_batch_for(exam_category: str | None) -> str | None:
    """艺体类 → 本科批艺体类批次名；普通类 → None。"""
    if is_art_sports(exam_category):
        return BATCH_ART_UNDERGRAD
    return None