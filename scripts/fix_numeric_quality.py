"""修复 numeric（官方院校代码）行的院校质量数据。

背景：
- canonical = official college code（numeric id，如 10001）。admission_ranks 1707 所均引用它。
- 之前 `import_excel_v3.py` 用错误列（col_level，实为"卓越工程师/部委直属"）解析层次，
  导致 numeric 行 level 落成 "普通"/"" 。
- 正确层次来源是专家表 `col_tags`（如 "985/211/双一流/国重点/保研资格"），与 CU 行 cross-check 一致。
- 薪资/就业/宿舍/城市活力/成本 均为公式模板值（seed_college_scores），本脚本按修正后的
  level + city 统一重新生成。

本脚本只更新 numeric 官方行，不改 admission_ranks，不删 CU 行。
用法：python scripts/fix_numeric_quality.py            # 实跑
       python scripts/fix_numeric_quality.py --dry-run # 仅审计
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from deeptutor.services.custom.db import get_connection, init_db

DEFAULT_EXCEL = Path.home() / "桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"

# 与 seed_college_scores.py 一致的城市档次（index）
CITY_TIER_IDX: dict[str, int] = {
    "北京市": 0, "上海市": 0, "广州市": 0, "深圳市": 0,
    "成都市": 1, "杭州市": 1, "武汉市": 1, "重庆市": 1,
    "南京市": 1, "天津市": 1, "苏州市": 1, "西安市": 1,
    "长沙市": 1, "沈阳市": 1, "青岛市": 1, "郑州市": 1,
    "大连市": 1, "东莞市": 1, "宁波市": 1, "厦门市": 1,
    "合肥市": 1, "佛山市": 1, "福州市": 1, "哈尔滨市": 1,
    "济南市": 1, "昆明市": 1, "长春市": 1, "温州市": 1,
    "无锡市": 1, "珠海市": 1, "贵阳市": 1, "南宁市": 1,
    "太原市": 1, "嘉兴市": 1, "南昌市": 1, "海口市": 1,
    "中山市": 2, "惠州市": 2, "常州市": 2, "徐州市": 2,
    "兰州市": 2, "绍兴市": 2, "扬州市": 2, "石家庄市": 2,
    "呼和浩特市": 2, "乌鲁木齐市": 2, "潍坊市": 2, "唐山市": 2,
    "金华市": 2, "三亚市": 2, "南通市": 2, "镇江市": 2,
    "泉州市": 2, "宜昌市": 2, "洛阳市": 2, "台州市": 2,
    "盐城市": 2, "芜湖市": 2, "廊坊市": 2, "湖州市": 2,
    "桂林市": 2, "赣州市": 2, "遵义市": 2, "莆田市": 2,
    "威海市": 2, "邯郸市": 2, "漳州市": 2, "岳阳市": 2,
    "淮安市": 2, "江门市": 2, "淄博市": 2, "柳州市": 2,
    "湛江市": 2, "黄冈市": 2, "株洲市": 2,
    "济宁市": 2, "大庆市": 2, "连云港市": 2, "保定市": 2,
    "鄂尔多斯市": 2, "包头市": 2, "宿迁市": 2, "绵阳市": 2,
    "临沂市": 2,
}
TIER_VITALITY = {0: 9.5, 1: 7.5, 2: 5.5, 3: 3.5}
TIER_COST = {0: 1.6, 1: 1.3, 2: 1.0, 3: 0.75}


def _normalize_city(name: str) -> str:
    if not name:
        return ""
    if not name.endswith("市") and len(name) <= 3:
        return name + "市"
    return name


def _city_tier_index(city: str) -> int:
    return CITY_TIER_IDX.get(_normalize_city(city or ""), 3)


def _level_from_tags(cl: str) -> str:
    """从专家表 col_tags（如 '985/211/双一流/国重点/保研资格'）生成组合 level。"""
    parts: list[str] = []
    for key in ("985", "211", "双一流"):
        if key in cl:
            parts.append(key)
    return "+".join(parts) if parts else ("普通" if cl else "")


def _score_dorm(level: str, tier: int) -> float:
    if "985" in level:
        base = 7.5
    elif "211" in level:
        base = 5.5
    elif "双一流" in level:
        base = 4.5
    else:
        base = 3.0
    bonus = {0: 1.0, 1: 0.5, 2: 0.0, 3: -0.5}.get(tier, 0)
    return round(max(1.0, min(10.0, base + bonus)), 2)


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
    return round(max(0.50, min(0.99, base)), 2)


def _score_salary(level: str, tier: int) -> float:
    if "985" in level:
        base = 14000
    elif "211" in level:
        base = 10500
    elif "双一流" in level:
        base = 9000
    else:
        base = 6500
    mult = {0: 1.35, 1: 1.15, 2: 1.0, 3: 0.85}.get(tier, 1.0)
    return round(base * mult, -2)


def _load_col_tags(excel_path: Path) -> dict[str, str]:
    """读取专家表：院校代码 -> col_tags（index 45）。"""
    wb = load_workbook(excel_path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    out: dict[str, str] = {}
    for i, row in enumerate(ws.iter_rows(min_row=4, values_only=True)):
        if i > 80000:
            break
        code = row[4]
        if code is not None:
            out.setdefault(str(code), str(row[45] or ""))
    return out


_DIRECT_CITY_TIER: dict[str, str] = {
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

# 直辖市省会 => 保底城市档次（numeric 的 city 可能是区名，此时按省/直辖市给城市级）
_MUNICIPALITY_CAPITAL_TIER: dict[str, str] = {
    "北京": "一线", "上海": "一线", "天津": "一线", "重庆": "新一线",
    "广州": "一线", "深圳": "一线", "杭州": "新一线", "南京": "新一线",
    "武汉": "新一线", "成都": "新一线", "西安": "新一线", "郑州": "新一线",
    "长沙": "新一线", "沈阳": "新一线", "青岛": "新一线", "济南": "新一线",
    "苏州": "新一线", "合肥": "新一线", "厦门": "新一线", "福州": "新一线",
    "哈尔滨": "新一线", "昆明": "新一线", "大连": "新一线", "宁波": "新一线",
    "东莞": "新一线", "佛山": "新一线", "珠海": "新一线", "无锡": "新一线",
    "长春": "新一线", "温州": "新一线", "南宁": "新一线", "贵阳": "新一线",
    "太原": "新一线", "嘉兴": "新一线", "南昌": "新一线", "海口": "新一线",
}


def _tier_from_city_tier(city: str, province: str) -> str:
    """numeric 行 city_tier 推导：city 若为区名/空白，用省份对应的直辖市/省会保底。"""
    city_norm = _normalize_city(city or "")
    if city_norm in _DIRECT_CITY_TIER:
        return _DIRECT_CITY_TIER[city_norm]
    if province in _MUNICIPALITY_CAPITAL_TIER:
        return _MUNICIPALITY_CAPITAL_TIER[province]
    return "三线"


def _region_from_province(province: str) -> str:
    return PROVINCE_REGION.get(province or "", "其他")


def run(dry: bool) -> None:
    init_db()
    conn = get_connection()

    # CU 同名 -> 用于 city_tier/region 军底
    cu_same: dict[str, dict[str, Any]] = {}
    for r in conn.execute(
        "SELECT id, name, city_tier, region, level FROM colleges WHERE id LIKE 'CU%'"
    ).fetchall():
        d = dict(r)
        cu_same.setdefault(d["name"], d)

    excel = DEFAULT_EXCEL
    if not excel.exists():
        print(f"[ERROR] 专家表不存在: {excel}")
        conn.close()
        return
    col_tags = _load_col_tags(excel)

    rows = conn.execute(
        "SELECT id, name, province, city, type, level, city_tier, region "
        "FROM colleges WHERE id NOT LIKE 'CU%' "
        "AND id IN (SELECT DISTINCT college_id FROM admission_ranks)"
    ).fetchall()

    fix_level = 0
    fix_tier = 0
    no_marker = 0
    cu_src_count = 0
    examples: list[dict[str, Any]] = []
    new_level_by_id: dict[str, str] = {}
    new_tier_by_id: dict[str, str] = {}

    for r in rows:
        cid = r["id"]
        cname = r["name"]
        old_level = r["level"]
        new_level = old_level

        # 1) level：主来源专家表 col_tags，军底 CU 同名
        src = col_tags.get(cid, "")
        if src:
            parsed = _level_from_tags(src)
        else:
            parsed = ""
            if cname in cu_same:
                parsed = cu_same[cname].get("level") or ""
                cu_src_count += 1
        if parsed and parsed != old_level:
            new_level = parsed
            fix_level += 1
        if not src and not parsed:
            no_marker += 1

        # 2) city_tier / region：
        #    - numeric 直辖市院校 city 常存区名（如"海淀区"）导致 city_tier 错算为"三线"，
        #      而 CU 行 city_tier 来自正确的市级名，更可靠 → 优先采用 CU 同名值。
        #    - CU 无同名时保留现状（或用省份/城市推导，见 _tier_from_province_city）。
        new_tier = r["city_tier"] or ""
        new_region = r["region"] or ""
        if cname in cu_same:
            cu = cu_same[cname]
            if cu.get("city_tier"):
                new_tier = cu["city_tier"]
            if cu.get("region"):
                new_region = cu["region"]
        else:
            # 无 CU 兜底：直辖市/省会用城市级推导
            derived = _tier_from_city_tier(r["city"] or "", r["province"] or "")
            if derived and (not new_tier or new_tier == "三线"):
                new_tier = derived
            if not new_region:
                new_region = _region_from_province(r["province"] or "")
        if new_tier != (r["city_tier"] or ""):
            fix_tier += 1

        new_level_by_id[cid] = new_level
        new_tier_by_id[cid] = new_tier

        examples.append({
            "id": cid, "name": cname,
            "level": f"{old_level!r} -> {new_level!r}",
            "city_tier": f"{r['city_tier']!r} -> {new_tier!r}",
        })

        if dry:
            continue
        conn.execute(
            "UPDATE colleges SET level=?, city_tier=?, region=? WHERE id=?",
            (new_level, new_tier, new_region, cid),
        )

    if dry:
        print("=== DRY RUN 审计 ===")
        print(f"总共 numeric 入学院校: {len(rows)}")
        print(f"  level 修正: {fix_level}（其中 CU 军底 {cu_src_count}）")
        print(f"  city_tier 修正: {fix_tier}")
        print("  无 985/211 marker（保持普通）:", no_marker)
        print("示例: ")
        for e in examples[:20]:
            print(f"   {e['id']} {e['name']}: level {e['level']} | {e['city_tier']}")
        conn.close()
        print("（dry-run 未写库，未生成质量分）")
        return

    conn.commit()

    # 3) 重跑质量公式（薪资/就业/dorm/city_vitality/cost）—— 仅对 numeric 入学院校
    #    用修正后的 level / city_tier（而非旧快照 / raw 区名）。
    _TIER_STR_INDEX = {"一线": 0, "新一线": 1, "二线": 2, "三线": 3, "其他": 3}

    def _city_index(tier_str: str) -> int:
        return _TIER_STR_INDEX.get(tier_str or "", 3)

    for r in rows:
        tier_i = _city_index(new_tier_by_id.get(r["id"], "三线"))
        level = (new_level_by_id.get(r["id"]) or "").strip() or "普通"
        dorm = _score_dorm(level, tier_i)
        vitality = TIER_VITALITY.get(tier_i, 3.5)
        cost = TIER_COST.get(tier_i, 0.75)
        emp = _score_employment(level, r["type"] or "")
        sal = _score_salary(level, tier_i)
        conn.execute(
            "UPDATE colleges SET dorm_score=?, city_vitality=?, cost_index=?, employment_rate=?, avg_salary=? WHERE id=?",
            (dorm, vitality, cost, emp, sal, r["id"]),
        )
    conn.commit()
    conn.close()
    print(f"\nDone (real run): level 修正 {fix_level}, tier 修正 {fix_tier}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="仅审计不写库")
    args = ap.parse_args()
    run(dry=args.dry_run)