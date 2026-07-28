from __future__ import annotations

import time
from typing import Any

from deeptutor.services.custom.college_dao import import_college
from deeptutor.services.custom.db import get_connection, init_db
from deeptutor.services.custom.models import College

def _normalize_city(name: str) -> str:
    if not name:
        return ""
    if not name.endswith("市") and len(name) <= 3:
        return name + "市"
    return name


CITY_TIER: dict[str, int] = {
    # 一线城市 (tier 0)
    "北京市": 0, "上海市": 0, "广州市": 0, "深圳市": 0,
    # 新一线 (tier 1)
    "成都市": 1, "杭州市": 1, "武汉市": 1, "重庆市": 1,
    "南京市": 1, "天津市": 1, "苏州市": 1, "西安市": 1,
    "长沙市": 1, "沈阳市": 1, "青岛市": 1, "郑州市": 1,
    "大连市": 1, "东莞市": 1, "宁波市": 1, "厦门市": 1,
    "合肥市": 1, "佛山市": 1, "福州市": 1, "哈尔滨市": 1,
    "济南市": 1, "昆明市": 1, "长春市": 1, "温州市": 1,
    "无锡市": 1, "珠海市": 1, "贵阳市": 1, "南宁市": 1,
    "太原市": 1, "嘉兴市": 1, "南昌市": 1, "海口市": 1,
    # 二线 (tier 2)
    "中山市": 2, "惠州市": 2, "常州市": 2, "徐州市": 2,
    "兰州市": 2, "绍兴市": 2, "扬州市": 2, "石家庄市": 2,
    "呼和浩特市": 2, "乌鲁木齐市": 2, "潍坊市": 2, "唐山市": 2,
    "金华市": 2, "三亚市": 2, "南通市": 2, "镇江市": 2,
    "泉州市": 2, "宜昌市": 2, "洛阳市": 2, "台州市": 2,
    "盐城市": 2, "芜湖市": 2, "廊坊市": 2, "湖州市": 2,
    "桂林市": 2, "赣州市": 2, "遵义市": 2, "莆田市": 2,
    "威海市": 2, "邯郸市": 2, "漳州市": 2, "岳阳市": 2,
    "淮安市": 2, "江门市": 2, "淄博市": 2, "柳州市": 2,
    "湛江市": 2, "黄冈市": 2, "威海市": 2, "株洲市": 2,
    "济宁市": 2, "大庆市": 2, "连云港市": 2, "保定市": 2,
    "鄂尔多斯市": 2, "包头市": 2, "宿迁市": 2, "绵阳市": 2,
    "临沂市": 2,
}

TIER_VITALITY = {0: 9.5, 1: 7.5, 2: 5.5, 3: 3.5}
TIER_COST = {0: 1.6, 1: 1.3, 2: 1.0, 3: 0.75}


def _score_dorm(level: str, tier: int) -> float:
    base = 0.0
    if "985" in level:
        base = 7.5
    elif "211" in level:
        base = 5.5
    elif "双一流" in level:
        base = 4.5
    else:
        base = 3.0
    tier_bonus = {0: 1.0, 1: 0.5, 2: 0.0, 3: -0.5}.get(tier, 0)
    return max(1.0, min(10.0, base + tier_bonus))


def _score_employment(level: str, college_type: str) -> float:
    if "985" in level:
        base = 0.93
    elif "211" in level:
        base = 0.88
    elif "双一流" in level:
        base = 0.85
    else:
        base = 0.78
    if college_type and "理工" in college_type:
        base += 0.04
    elif college_type and "医药" in college_type:
        base += 0.02
    elif college_type and "师范" in college_type:
        base -= 0.02
    elif college_type and ("艺术" in college_type or "体育" in college_type):
        base -= 0.05
    return max(0.50, min(0.99, base))


def _score_salary(level: str, tier: int) -> float:
    if "985" in level:
        base = 14000
    elif "211" in level:
        base = 10500
    elif "双一流" in level:
        base = 9000
    else:
        base = 6500
    city_mult = {0: 1.35, 1: 1.15, 2: 1.0, 3: 0.85}.get(tier, 1.0)
    return round(base * city_mult, -2)


def run():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, city, level, type FROM colleges"
    ).fetchall()
    conn.close()

    total = len(rows)
    updated = 0
    t0 = time.time()

    for i, row in enumerate(rows):
        city = str(row["city"] or "")
        level = str(row["level"] or "普通")
        college_type = str(row["type"] or "")
        tier = CITY_TIER.get(_normalize_city(city), 3)
        try:
            college = College(
                id=row["id"],
                name=row["name"],
                province="",
                city=city,
                type=college_type,
                level=level,
                dorm_score=_score_dorm(level, tier),
                city_vitality=TIER_VITALITY.get(tier, 3.5),
                cost_index=TIER_COST.get(tier, 0.75),
                employment_rate=_score_employment(level, college_type),
                avg_salary=_score_salary(level, tier),
            )
            import_college(college)
            updated += 1
        except Exception as e:
            print(f"  [{i+1}] SKIP {row['name']}: {e}")

        if (i + 1) % 500 == 0:
            print(f"  Progress: {i+1}/{total}")

    elapsed = time.time() - t0
    print(f"\nDone: {updated}/{total} colleges scored in {elapsed:.1f}s")
    conn2 = get_connection()
    th = conn2.execute("SELECT name, level, city, dorm_score, city_vitality, avg_salary "
                       "FROM colleges WHERE name LIKE '%清华%' AND level LIKE '%985%'").fetchone()
    conn2.close()
    if th:
        print(f"Sample: {th['name']} dorm={th['dorm_score']:.1f}, "
              f"city_vitality={th['city_vitality']:.1f}, "
              f"salary={th['avg_salary']:.0f}")


if __name__ == "__main__":
    run()
