"""用官方行政区划数据回填 colleges.city_tier / region。

数据源：民政部国家地名信息库（2025版）镜像
  /tmp/opencode/data.csv  — 4级全量（level1 省 / level2 地级 / level3 县级）
  /tmp/opencode/pc-code.json — 省↔地级联动

规则：
  1. region 一律由 province 推导（PROVINCE_REGION）——修复 1816 所空 region，
     同时消灭前端 `c.region || "其他"` 分组里"其他"爆炸。
  2. city_tier 优先级：
     a. 直辖市辖区（海淀区/浦东新区…）→ 继承直辖市等级（北京/上海=一线，天津/重庆=新一线）
     b. 手工商业分级 CITY_TIER_MAP（含自治州全称/县级市手工档）
     c. 官方 L2 命中（地级市/自治州/地区/盟）但无手工档 → "其他"
     d. 未命中官方名单（错别字/伪行政区名/香港等）→ "其他" + 诊断清单
  3. 幂等可重跑；--dry-run 只打印不改库。

用法：
  python scripts/backfill_region_official.py [--csv PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from deeptutor.services.custom.db import get_connection, init_db

DEFAULT_CSV = "/tmp/opencode/data.csv"
DEFAULT_PC_JSON = "/tmp/opencode/pc-code.json"

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

# 直辖市简码 → 等级（城市等级继承用）
MUNI_TIER = {"北京": "一线", "上海": "一线", "天津": "新一线", "重庆": "新一线"}

# 官方镜像缺失、但确为直辖市辖区的补充映射（重庆渝北/江北等；纂江区为綦江区错别字）
MUNI_DISTRICT_OVERRIDES = {
    "渝北区": "重庆", "江北区": "重庆", "纂江区": "重庆",
}

# 自治州/地区简称 → 官方全称（用于 CITY_TIER_MAP 命中；未命中则归"其他"）
AUT_STATE_ABBR = {
    "大理": "大理白族自治州", "红河": "红河哈尼族彝族自治州",
    "恩施": "恩施土家族苗族自治州", "湘西": "湘西土家族苗族自治州",
    "喀什": "喀什地区", "黔东南": "黔东南苗族侗族自治州",
    "凉山": "凉山彝族自治州", "和田": "和田地区",
    "巴音郭楞": "巴音郭楞蒙古自治州", "阿克苏": "阿克苏地区",
    "延边": "延边朝鲜族自治州", "伊犁": "伊犁哈萨克自治州",
    "楚雄": "楚雄彝族自治州", "黔南": "黔南布依族苗族自治州",
    "黔西南": "黔西南布依族苗族自治州", "塔城": "塔城地区",
    "西双版纳": "西双版纳傣族自治州", "昌吉": "昌吉回族自治州",
    "文山": "文山壮族苗族自治州",
}


def _normalize_city(name: str) -> str:
    if not name:
        return ""
    if not name.endswith("市") and len(name) <= 3:
        return name + "市"
    return name


def load_official(csv_path: str) -> tuple[dict[str, str], set[str]]:
    """返回 (district->muni, level2 官方名集合)。"""
    district2muni: dict[str, str] = {}
    l2_names: set[str] = set()
    path = Path(csv_path)
    if not path.exists():
        print(f"[warn] 官方数据不存在: {csv_path}，仅用手工覆盖", file=sys.stderr)
        return district2muni, l2_names
    munis: dict[str, str] = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["type"] == "直辖市":
                munis[r["code"]] = r["name"].replace("市", "")
            elif r["level"] == "2":
                l2_names.add(r["name"])
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r["level"] == "3" and r["father_code"] in munis:
            district2muni[r["name"]] = munis[r["father_code"]]
    district2muni.update(MUNI_DISTRICT_OVERRIDES)
    return district2muni, l2_names


def resolve_tier(city: str, province: str, district2muni: dict[str, str], l2_names: set[str]) -> str:
    """按规则链确定 city_tier。

    优先级：手工商业分级 > 直辖市辖区继承 > 官方 L2 命中(保持三线底线) > 其他(待手工)。
    """
    if not city:
        return "其他"
    norm = _normalize_city(city)
    if norm in CITY_TIER_MAP:
        return CITY_TIER_MAP[norm]
    if city + "市" in CITY_TIER_MAP:
        return CITY_TIER_MAP[city + "市"]
    # 直辖市辖区（含 璧山 → 璧山区 归一）→ 继承直辖市等级
    district = city if city.endswith("区") or city in district2muni else city + "区"
    if district in district2muni:
        muni = district2muni[district]
        return MUNI_TIER.get(muni, "其他")
    # 自治州简称 → 官方全称 → 手工档；未命中则归入官方 L2 兜底
    if city in AUT_STATE_ABBR:
        full = AUT_STATE_ABBR[city]
        return CITY_TIER_MAP.get(full + "市", "三线")
    # 官方 L2 命中（地级市/自治州全称/地区/盟）→ 三线底线
    for cand in (norm, city, city + "市", norm + "市"):
        if cand in l2_names:
            return "三线"
    return "其他"


def run(csv_path: str, dry_run: bool = False) -> None:
    init_db()
    district2muni, l2_names = load_official(csv_path)
    conn = get_connection()
    rows = conn.execute("SELECT id, province, city, city_tier, region FROM colleges").fetchall()
    total = len(rows)
    tier_changed = 0
    region_changed = 0
    tier_dist = Counter()
    region_dist = Counter()
    unmatched: Counter[str] = Counter()
    tier_before = Counter()
    tier_after = Counter()

    for r in rows:
        province = r["province"] or ""
        city = r["city"] or ""
        cid = r["id"]

        tier = resolve_tier(city, province, district2muni, l2_names)
        region = PROVINCE_REGION.get(province, "其他")

        tier_before[r["city_tier"] or "（空）"] += 1
        tier_after[tier] += 1
        if tier != (r["city_tier"] or ""):
            tier_changed += 1
            if not dry_run:
                conn.execute("UPDATE colleges SET city_tier=? WHERE id=?", (tier, cid))
        if region != (r["region"] or ""):
            region_changed += 1
            if not dry_run:
                conn.execute("UPDATE colleges SET region=? WHERE id=?", (region, cid))

        tier_dist[tier] += 1
        region_dist[region] += 1
        if tier == "其他" and city:
            unmatched[city] += 1

    if not dry_run:
        conn.commit()

    print(f"\n=== 回填报告 ({'DRY-RUN' if dry_run else '已执行'}) ===")
    print(f"总院校: {total}")
    print(f"city_tier 变更: {tier_changed}  | region 变更: {region_changed}")
    print(f"\ncity_tier 分布 (变更前 -> 变更后):")
    for k in sorted(set(tier_before) | set(tier_after), key=lambda x: {"一线":0,"新一线":1,"二线":2,"三线":3,"其他":4,"（空）":5}.get(x,9)):
        print(f"  {k:8s}: {tier_before.get(k,0):5d} -> {tier_after.get(k,0):5d}")
    print(f"\nregion 分布:")
    for k, v in region_dist.most_common():
        print(f"  {k:6s}: {v:5d}")
    print(f"\n归入'其他'的城市 (共 {len(unmatched)} 个，{sum(unmatched.values())} 所院校，待手工分级):")
    for city, cnt in unmatched.most_common():
        print(f"  {city:20s} {cnt:4d}")

    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="官方行政区划回填 city_tier/region")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="官方 data.csv 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印不改库")
    args = ap.parse_args()
    run(args.csv, dry_run=args.dry_run)