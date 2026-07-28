from __future__ import annotations

import time

from deeptutor.services.custom.db import get_connection, init_db

CITY_TIER_MAP: dict[str, str] = {
    "北京市": "一线", "上海市": "一线", "广州市": "一线", "深圳市": "一线",
    "成都市": "新一线", "杭州市": "新一线", "武汉市": "新一线", "重庆市": "新一线",
    "南京市": "新一线", "天津市": "新一线", "苏州市": "新一线", "西安市": "新一线",
    "长沙市": "新一线", "沈阳市": "新一线", "青岛市": "新一线", "郑州市": "新一线",
    "大连市": "新一线", "东莞市": "新一线", "宁波市": "新一线", "厦门市": "新一线",
    "合肥市": "新一线", "佛山市": "新一线", "福州市": "新一线", "哈尔滨市": "新一线",
    "济南市": "新一线", "昆明市": "新一线", "长春市": "新一线", "温州市": "新一线",
    "无锡市": "新一线", "珠海市": "新一线", "贵阳市": "新一线", "南宁市": "新一线",
    "太原市": "新一线", "嘉兴市": "新一线", "南昌市": "新一线", "海口市": "新一线",
    "中山市": "二线", "惠州市": "二线", "常州市": "二线", "徐州市": "二线",
    "兰州市": "二线", "绍兴市": "二线", "扬州市": "二线", "石家庄市": "二线",
    "呼和浩特市": "二线", "乌鲁木齐市": "二线", "潍坊市": "二线", "唐山市": "二线",
    "金华市": "二线", "三亚市": "二线", "南通市": "二线", "镇江市": "二线",
    "泉州市": "二线", "宜昌市": "二线", "洛阳市": "二线", "台州市": "二线",
    "盐城市": "二线", "芜湖市": "二线", "廊坊市": "二线", "湖州市": "二线",
    "桂林市": "二线", "赣州市": "二线", "遵义市": "二线", "莆田市": "二线",
    "威海市": "二线", "邯郸市": "二线", "漳州市": "二线", "岳阳市": "二线",
    "淮安市": "二线", "江门市": "二线", "淄博市": "二线", "柳州市": "二线",
    "湛江市": "二线", "黄冈市": "二线", "株洲市": "二线",
    "济宁市": "二线", "大庆市": "二线", "连云港市": "二线", "保定市": "二线",
    "鄂尔多斯市": "二线", "包头市": "二线", "宿迁市": "二线", "绵阳市": "二线",
    "临沂市": "二线",
}

PROVINCE_REGION: dict[str, str] = {
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东",
    "福建": "华东", "江西": "华东", "山东": "华东",
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    "广东": "华南", "广西": "华南", "海南": "华南",
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南", "西藏": "西南",
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
    "香港": "港澳台", "澳门": "港澳台", "台湾": "港澳台",
}

def _normalize_city(name: str) -> str:
    if not name:
        return ""
    if not name.endswith("市") and len(name) <= 3:
        return name + "市"
    return name

def run():
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT id, province, city FROM colleges").fetchall()
    total = len(rows)
    updated_tier = 0
    updated_region = 0

    for r in rows:
        cid = r["id"]
        province = r["province"] or ""
        city = r["city"] or ""
        city_norm = _normalize_city(city)

        tier = CITY_TIER_MAP.get(city_norm, "三线")
        conn.execute("UPDATE colleges SET city_tier=? WHERE id=?", (tier, cid))
        updated_tier += 1

        region = PROVINCE_REGION.get(province, "其他")
        conn.execute("UPDATE colleges SET region=? WHERE id=?", (region, cid))
        updated_region += 1

        if (updated_tier % 500) == 0:
            print(f"  progress: {updated_tier}/{total}")

    conn.commit()
    conn.close()
    print(f"Done: {updated_tier} city_tier, {updated_region} region updated out of {total} colleges")

if __name__ == "__main__":
    run()
