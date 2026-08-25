from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()

def _plan_label(p: dict[str, Any]) -> str:
    """志愿表命名：志愿表{月日时分}（紧凑式，如 志愿表06281626）。"""
    import time as _t
    import datetime as _dt
    ts = p.get("created_at") or 0
    dt = _dt.datetime.fromtimestamp(ts)
    return f"{dt.month:02d}{dt.day:02d}{dt.hour:02d}{dt.minute:02d}"

PROVINCE_RULES: dict[str, dict[str, Any]] = {
    "江苏": {"groups": 40, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "浙江": {"groups": 80, "mode": "专业", "ratio": [3, 4, 3]},
    "广东": {"groups": 45, "mode": "院校专业组", "ratio": [3, 4, 3]},
    "北京": {"groups": 30, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "上海": {"groups": 24, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "default": {"groups": 30, "mode": "院校", "ratio": [3, 3, 4]},
}

# 提前批各类别志愿设置（官方《2026年志愿填报通知》+《考生志愿表》，AGENTS.md Phase 23.2）
EARLY_BATCH_RULES: dict[str, dict[str, Any]] = {
    "提前批本科-军检类": {"groups": 10, "mode": "院校专业组", "ratio": [3, 4, 3], "parallel": True},
    "提前批本科-非军检类": {"groups": 20, "mode": "院校专业组", "ratio": [3, 4, 3], "parallel": True},
    "提前批本科-教师专项": {"groups": 10, "mode": "院校专业组", "ratio": [3, 4, 3], "parallel": True},
    "提前批本科-卫生专项": {"groups": 10, "mode": "院校专业组", "ratio": [3, 4, 3], "parallel": True},
    "提前批本科-特殊类型招生": {"groups": 1, "mode": "院校专业组", "ratio": None, "parallel": False},
    "提前批本科-空军海军招飞": {"groups": 1, "mode": "院校专业组", "ratio": None, "parallel": False},
    "提前批本科-艺术类统考+校考": {"groups": 1, "mode": "院校专业组", "ratio": None, "parallel": False},
    "提前批本科-艺术类校考": {"groups": 1, "mode": "院校专业组", "ratio": None, "parallel": False},
}


class SlotItem(BaseModel):
    college_id: str
    college_name: str = ""
    group_code: str = ""
    group_name: str = ""
    group_prob: float = 0.5
    tier: str = "steady"
    order: int = 0
    adjustable: bool = True
    reason: str = ""
    majors: list[dict] = []
    province_code: str = ""
    bargain_score: float = 0
    rank_source: str = "official"
    reference_rank: float = 0
    reference_source: str = ""


class CreatePlanRequest(BaseModel):
    user_id: str = "default"
    province: str = "广东"
    year: int = 2026
    exam_category: str = "物理"
    rank: int | None = None
    score: int | None = None
    bonus_points: int = 0
    level: str | None = None
    strategies: list[str] | None = None
    strategy: str | None = None  # deprecated, use strategies
    major_categories: list[str] | None = None
    score_rank_range: tuple[int, int] | None = None
    city_tier: str | None = None
    regions: list[str] | None = None
    cities: list[str] | None = None
    batch: str = "本科批"
    art_category: str | None = None
    art_direction: str | None = None
    culture_score: int | None = None
    major_score: int | None = None
    composite_score: float | None = None
    medical_restrictions: list[str] | None = None
    special_type: str | None = None
    program_type: str | None = None


class UpdateSlotsRequest(BaseModel):
    slots: list[SlotItem]
    status: str | None = None


class ClonePlanRequest(BaseModel):
    user_id: str = "default"
    name: str | None = None


@router.post("/volunteer/plan/create")
async def create_plan(body: CreatePlanRequest):
    from deeptutor.services.custom.college_dao import search_colleges
    from deeptutor.services.custom.db import get_connection
    from deeptutor.services.custom.volunteer_scorer import generate_group_recommendations
    from deeptutor.services.custom.volunteer_table_dao import create_plan as dao_create
    from deeptutor.services.custom.user_settings_dao import get_user_weights
    from deeptutor.services.custom.art_sports import is_art_sports, ART_SPORTS_RULES

    is_art = is_art_sports(body.exam_category)
    rules: dict[str, Any] | None = None
    if body.batch in EARLY_BATCH_RULES:
        # 提前批各类别志愿设置（军检10/非军检20/教师10/卫生10/特殊1/招飞1/艺术类提前批1）
        rules = EARLY_BATCH_RULES[body.batch]
    elif is_art:
        # 艺体类：本科批用官方 20 组规则；不按普通类批次名，统一"艺体类本科批"
        body.batch = "艺体类本科批"
        art_rules = ART_SPORTS_RULES["本科批"]
        rules = {
            "groups": art_rules["groups"],
            "mode": art_rules["mode"],
            "ratio": art_rules["ratio"],
        }

    conn = get_connection()
    ids = [
        r["college_id"]
        for r in conn.execute(
            "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ? AND year < ?",
            (body.province, body.exam_category, body.year),
        ).fetchall()
    ]
    conn.close()

    from deeptutor.api.routers.volunteer import _resolve_strategies
    effective_strategies = _resolve_strategies(body.strategies, body.strategy)

    colleges = search_colleges(
        college_ids=ids, limit=2000,
        city_tier=body.city_tier, regions=body.regions, cities=body.cities,
    )
    if not colleges:
        raise HTTPException(status_code=400, detail="No colleges found for given province")

    colleges_map = {c["id"]: c for c in colleges}

    from deeptutor.services.custom.art_sports import default_art_direction, resolve_art_rank

    effective_rank = body.rank
    if is_art:
        art_rank, _ = resolve_art_rank(
            province=body.province,
            category_code=body.art_category or "美术与设计",
            direction=body.art_direction or default_art_direction(body.art_category or "美术与设计"),
            user_rank=body.rank,
            composite_score=body.composite_score,
            culture_score=body.culture_score,
            major_score=body.major_score,
            bonus_points=body.bonus_points,
        )
        if art_rank:
            effective_rank = art_rank
    elif not effective_rank:
        raise HTTPException(status_code=400, detail="请填写位次")

    profile = {
        "rank": effective_rank or 0,
        "province": body.province,
        "exam_category": body.exam_category,
        "user_id": body.user_id,
        "score": body.score,
        "year": body.year,
        "medical_restrictions": body.medical_restrictions or [],
    }
    if is_art:
        if body.composite_score:
            profile["composite_score"] = body.composite_score
        elif body.culture_score and body.major_score:
            from deeptutor.services.custom.art_sports import calc_composite_score
            cs = calc_composite_score(body.art_category or "美术与设计", body.culture_score, body.major_score)
            if not cs.get("errors") and cs["score"]:
                profile["composite_score"] = cs["score"]
    weights = get_user_weights(body.user_id)
    try:
        rec_result = generate_group_recommendations(
            colleges_map,
            province=body.province,
            exam_category=body.exam_category,
            user_profile=profile,
            weights=weights,
            top_n=100,
            strategy=effective_strategies,
            major_categories=body.major_categories,
            score_rank_range=body.score_rank_range,
            batch=body.batch,
            art_category=body.art_category,
            special_type=body.special_type,
            program_type=body.program_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成推荐失败: {str(e)}")

    if is_art and rec_result.get("data_status") == "no_data":
        raise HTTPException(status_code=400, detail=rec_result.get("message", "艺体类投档数据待补充"))

    if rules is None:
        rules = PROVINCE_RULES.get(body.province, PROVINCE_RULES["default"])
    ratio = rules["ratio"]
    total_groups = rules["groups"]

    reach_pool = rec_result["tiers"].get("reach", [])
    steady_pool = rec_result["tiers"].get("steady", [])
    safe_pool = rec_result["tiers"].get("safe", [])

    if not ratio or total_groups == 1:
        # 顺序志愿（特殊类型/招飞/艺术类提前批）：1 个院校专业组志愿，取总分最高
        combined = reach_pool + steady_pool + safe_pool
        if not combined:
            raise HTTPException(status_code=400, detail="该批次无投档数据，暂无法生成志愿表（顺序志愿须对照招生章程）")
        single = max(combined, key=lambda x: x["total_score"])
        prob = single["group_prob"]
        single_tier = "safe" if prob >= 0.65 else "steady" if prob >= 0.35 else "reach"
        selected_pools: list[tuple[list[dict], str, int]] = [([single], single_tier, 1)]
    else:
        ratio_sum = sum(ratio)
        reach_count = min(total_groups * ratio[0] // ratio_sum, len(reach_pool))
        steady_count = min(total_groups * ratio[1] // ratio_sum, len(steady_pool))
        safe_count = min(total_groups * ratio[2] // ratio_sum, len(safe_pool))

        remaining = total_groups - (reach_count + steady_count + safe_count)
        if remaining > 0:
            extra = (reach_pool[reach_count:] if reach_count < len(reach_pool) else []) \
                  + (steady_pool[steady_count:] if steady_count < len(steady_pool) else []) \
                  + (safe_pool[safe_count:] if safe_count < len(safe_pool) else [])
            extra.sort(key=lambda x: -x["total_score"])
            for item in extra[:remaining]:
                prob = item["group_prob"]
                if prob >= 0.65:
                    safe_pool.insert(safe_count, item)
                    safe_count += 1
                elif prob >= 0.35:
                    steady_pool.insert(steady_count, item)
                    steady_count += 1
                else:
                    reach_pool.insert(reach_count, item)
                    reach_count += 1
        selected_pools = [
            (reach_pool, "reach", reach_count),
            (steady_pool, "steady", steady_count),
            (safe_pool, "safe", safe_count),
        ]

    # Look up major names
    conn = get_connection()
    major_names = {
        r["id"]: r["name"]
        for r in conn.execute("SELECT id, name FROM majors").fetchall()
    }
    # 本省招生代码：official_code -> province_code（用于志愿表卡片展示）
    import re as _re
    province_codes: dict[str, str] = {}
    for r in conn.execute(
        "SELECT official_code, province_code FROM college_code_map WHERE province = ?",
        (body.province,),
    ).fetchall():
        province_codes.setdefault(r["official_code"], r["province_code"])
    conn.close()

    def _lookup_province_code(college_id: str) -> str:
        if not college_id:
            return ""
        if college_id in province_codes:
            return province_codes[college_id] or ""
        base = _re.sub(r"-[A-Za-z0-9]+$", "", college_id)
        return province_codes.get(base, "")

    slots: list[dict[str, Any]] = []
    order = 1
    for pool, tier, count in selected_pools:
        for item in pool[:count]:
            college = item["college"]
            majors = []
            max_majors = 6 if is_art else len(item["majors"])
            for m in item["majors"][:max_majors]:
                mid = m["major_id"]
                majors.append({
                    "major_id": mid,
                    "major_name": m.get("major_name") or major_names.get(mid, mid),
                    "years": m.get("years", ""),
                    "campus": m.get("campus", ""),
                    "tuition": m.get("tuition", 0),
                    "medical_note": m.get("medical_note", ""),
                    "requirement": m.get("requirement", ""),
                    "admission_prob": m["admission_prob"],
                    "order": len(majors) + 1,
                    "tag": m.get("tag", "可选"),
                })

            slots.append({
                "college_id": college["id"],
                "college_name": college["name"],
                "province_code": _lookup_province_code(college["id"]),
                "group_code": item["group_code"],
                "group_name": f"{item['group_code']}组",
                "group_prob": item["group_prob"],
                "rank_source": item.get("rank_source", "official"),
                "tier": tier,
                "order": order,
                "adjustable": True,
                "reason": f"{'冲刺' if tier == 'reach' else '稳妥' if tier == 'steady' else '保底'}志愿推荐",
                "majors": majors,
                "bargain_score": item.get("bargain_score", 0),
                "reference_rank": item.get("reference_rank", 0),
                "reference_source": item.get("reference_source", ""),
            })
            order += 1

    # 去重：内容与任一活跃方案完全一致则拒绝（保留顺序 + rank，rank 不同即不同）
    from deeptutor.services.custom.volunteer_table_dao import find_duplicate
    dup = find_duplicate(body.user_id, slots, rank=effective_rank, exam_category=body.exam_category)
    if dup:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"与志愿表{_plan_label(dup)}完全相同，未保存",
                "duplicate_plan_id": dup["id"],
                "duplicate_label": _plan_label(dup),
            },
        )

    plan = dao_create(
        body.user_id, body.province, body.exam_category, effective_rank, rules, slots,
        batch=body.batch, score=body.score, medical_restrictions=body.medical_restrictions or [],
    )
    if is_art and len(slots) > 0 and len(steady_pool) == 0 and len(safe_pool) == 0:
        conn = get_connection()
        row = conn.execute(
            "SELECT MAX(min_rank) AS mx FROM admission_ranks WHERE province=? AND exam_category=? AND art_category=? AND min_rank > 0 AND year < ?",
            (body.province, body.exam_category, body.art_category or "美术与设计", body.year),
        ).fetchone()
        conn.close()
        max_rank = row["mx"] if row and row["mx"] else 0
        plan = {
            **plan,
            "warning": (
                f"您的位次较高，超出艺体类投档数据中稳妥/保底覆盖范围"
                f"（本类投档最高位次约 {max_rank}），当前志愿全部为冲刺。"
            ),
        }
    return plan


@router.get("/volunteer/plan/trash")
async def list_trash(user_id: str = "default"):
    from deeptutor.services.custom.volunteer_table_dao import list_trash as dao_trash

    now = __import__("time").time()
    return {
        "plans": [
            {
                **p,
                "remaining_days": max(0, int((p.get("deleted_at") or now) + 7 * 24 * 3600 - now) // 86400),
            }
            for p in dao_trash(user_id)
        ]
    }


@router.get("/volunteer/plan/list")
async def list_plans(user_id: str = "default"):
    from deeptutor.services.custom.volunteer_table_dao import list_plans as dao_list

    return {"plans": dao_list(user_id)}


@router.get("/volunteer/plan/{plan_id}")
async def get_plan(plan_id: str):
    from deeptutor.services.custom.volunteer_table_dao import get_plan as dao_get

    plan = dao_get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.put("/volunteer/plan/{plan_id}")
async def update_plan(plan_id: str, body: UpdateSlotsRequest):
    from deeptutor.services.custom.volunteer_table_dao import update_plan as dao_update

    slots_dict = [s.model_dump() for s in body.slots]
    plan = dao_update(plan_id, slots_dict, status=body.status)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/volunteer/plan/{plan_id}")
async def delete_plan(plan_id: str):
    """软删除：移入回收站（保留 7 天）。"""
    from deeptutor.services.custom.volunteer_table_dao import soft_delete_plan

    if not soft_delete_plan(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True}


@router.post("/volunteer/plan/{plan_id}/restore")
async def restore_plan(plan_id: str):
    from deeptutor.services.custom.volunteer_table_dao import restore_plan as dao_restore

    plan = dao_restore(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"plan": plan}


@router.post("/volunteer/plan/{plan_id}/purge")
async def purge_plan(plan_id: str):
    from deeptutor.services.custom.volunteer_table_dao import purge_plan as dao_purge

    if not dao_purge(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True}


@router.put("/volunteer/plan/{plan_id}/reorder")
async def reorder_plan(plan_id: str):
    from deeptutor.services.custom.volunteer_table_dao import get_plan, update_plan

    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    slots = plan["slots"]
    slots.sort(key=lambda s: -s.get("group_prob", s.get("admission_prob", 0.5)))
    for i, s in enumerate(slots, 1):
        s["order"] = i
        prob = s.get("group_prob", s.get("admission_prob", 0))
        s["reason"] = f"第{i}志愿 (概率 {prob:.1%})"

    updated = update_plan(plan_id, slots)
    return {"plan": updated, "message": "已按录取概率降序重排"}


@router.post("/volunteer/plan/{plan_id}/ai-tune")
async def ai_tune_plan(plan_id: str):
    """AI 优化建议：对当前志愿表逐条点评 + 给替换/重排意见。

    只返回建议文本，**不修改、不生成**志愿表。建议基于真实专业组候选池，
    LLM 只在一片真实数据上做分析。
    """
    from deeptutor.services.custom.college_dao import search_colleges
    from deeptutor.services.custom.db import get_connection as db_conn
    from deeptutor.services.custom.volunteer_scorer import generate_group_recommendations
    from deeptutor.services.custom.volunteer_table_dao import get_plan
    from deeptutor.services.custom.user_settings_dao import get_user_weights
    from deeptutor.services.llm import complete
    from deeptutor.api.routers.volunteer import _resolve_strategies

    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    slots = plan["slots"]
    if not slots:
        raise HTTPException(status_code=400, detail="志愿表为空")

    # 1. 从真实录取数据取本科目候选（与 create_plan 同一引擎）
    conn = db_conn()
    plan_batch = plan.get("batch") or "本科批"
    target_year = int(plan.get("year", 2026) or 2026)
    ids = [
        r["college_id"]
        for r in conn.execute(
            "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ? AND year < ?",
            (plan["province"], plan["exam_category"], target_year),
        ).fetchall()
    ]
    conn.close()

    colleges = search_colleges(college_ids=ids, limit=2000)
    if not colleges:
        raise HTTPException(status_code=400, detail="No colleges found for province")
    colleges_map = {c["id"]: c for c in colleges}

    user_id = plan.get("user_id") or "default"
    profile = {
        "rank": plan["rank"],
        "province": plan["province"],
        "exam_category": plan["exam_category"],
        "user_id": user_id,
        "year": target_year,
    }
    weights = get_user_weights(user_id)
    try:
        rec_result = generate_group_recommendations(
            colleges_map,
            province=plan["province"],
            exam_category=plan["exam_category"],
            user_profile=profile,
            weights=weights,
            top_n=300,
            strategy=_resolve_strategies(None, None),
            batch=plan_batch,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成候选失败: {str(e)}")

    # 2. 每档候选按综合质量分层抽取：概率桶（梯度覆盖）+ 桶内质量分（优选）
    CITY_TIER_WEIGHTS = {"一线": 1.0, "新一线": 0.85, "二线": 0.7, "三线": 0.55, "其他": 0.4}

    def _level_weight(level: str | None) -> float:
        level = level or ""
        if "985" in level:
            return 1.0
        if "211" in level:
            return 0.85
        if "双一流" in level:
            return 0.8
        return 0.6

    def _quality_score(c: dict[str, Any]) -> float:
        col = c.get("college", {})
        level_w = _level_weight(col.get("level"))
        employment = min(1.0, max(0.0, col.get("employment_rate") or 0))
        salary = min(1.0, (col.get("avg_salary") or 0) / 15_000.0)
        city_w = CITY_TIER_WEIGHTS.get(col.get("city_tier") or "", 0.4)
        return level_w * 0.30 + employment * 0.25 + salary * 0.25 + city_w * 0.20

    def _pick_tier(tier: str) -> list[dict[str, Any]]:
        items = [{**it, "_tier": tier} for it in rec_result["tiers"].get(tier, [])]
        items.sort(key=lambda x: -x["group_prob"])
        if len(items) <= 15:
            return items
        # 均分 3 个概率桶，每桶内按质量分取 top5，共 15 条
        buckets = [items[i::3] for i in range(3)]
        picked: list[dict[str, Any]] = []
        for b in buckets:
            b.sort(key=lambda x: -_quality_score(x))
            picked.extend(b[:5])
        return picked

    candidates: list[dict[str, Any]] = []
    for tier in ("reach", "steady", "safe"):
        candidates.extend(_pick_tier(tier))
    candidates.sort(key=lambda x: -x["group_prob"])

    # 3. 构建 LLM 上下文：当前表 + 精选候选池（含学校质量标注）
    slot_text = "\n".join(
        f"#{s['order']} {s['college_name']} "
        f"[{s.get('tier','')}] 组{s.get('group_code','')} 概率{s.get('group_prob', s.get('admission_prob', 0)):.0%}"
        for s in slots
    )

    def _cand_line(i: int, c: dict[str, Any]) -> str:
        col = c.get("college", {})
        level = col.get("level") or "普通"
        emp = col.get("employment_rate")
        emp_txt = f"{emp:.1%}" if isinstance(emp, (int, float)) else "-"
        salary = col.get("avg_salary")
        salary_txt = f"{salary/1000:.1f}k" if isinstance(salary, (int, float)) and salary else "-"
        city = col.get("city_tier") or "-"
        return (
            f"{i+1}. {col.get('name','?')} 组{c['group_code']} 概率{c['group_prob']:.0%}（{c['_tier']}）"
            f" | 层次:{level} 就业率:{emp_txt} 薪资:{salary_txt} 城市:{city}"
        )

    cand_text = "\n".join(_cand_line(i, c) for i, c in enumerate(candidates))

    prompt = (
        f"你是资深高考志愿填报顾问。省份：{plan['province']}，科类：{plan['exam_category']}，位次：{plan['rank']}。\n\n"
        f"用户当前志愿表（按志愿顺序）：\n{slot_text}\n\n"
        f"以下是系统基于真实录取数据为这位考生算出的候选池（编号-院校 组号 录取概率 层次/就业率/薪资/城市，全部真实）：\n{cand_text}\n\n"
        "请对用户当前志愿表逐条点评并给出优化建议。要求：\n"
        "1. 对每个志愿给出 action（keep=保留 / swap=建议替换），如替换请给出建议的候选池编号和理由\n"
        "2. 关注冲稳保梯度、倒序、保底是否足够稳固、相邻志愿差距是否过小\n"
        "3. 在概率合适的前提下，优先推荐层次更高、就业更强、薪资更优、城市更好的院校（参考候选池中的标注）\n"
        "4. **不得虚构院校或候选编号**，引用的替换目标必须来自上面候选池\n"
        "5. 最后给一段整体总结（字数不超过120）。\n\n"
        "以JSON输出，格式：\n"
        "{\"summary\": \"整体总结\", \"advice\": [{\"order\": 1, \"action\": \"keep|swap\", \"suggest_index\": 编号(仅swap时需要，0表示不指定), \"reason\": \"点评与理由\"}]}\n"
        "**要求**：\"advice\" 数组只需包含真正需要调整的志愿（action=\"swap\" 的，或 keep 但值得提醒的），不要逐条把所有志愿都列出来——只点评有问题的、能改进的志愿即可，数量控制在 5-15 条。"
    )

    try:
        reply = await asyncio.wait_for(
            complete(
                prompt=prompt,
                system_prompt="你是一个志愿填报专家，只输出JSON。",
                temperature=0.3,
                max_tokens=2048,
                model="deepseek-v4-flash",
            ),
            timeout=30,
        )
        import json
        import re

        json_match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not json_match:
            raise ValueError("LLM返回格式错误")
        parsed = json.loads(json_match.group())
        advice = parsed.get("advice", [])
        if not advice:
            raise ValueError("LLM未返回有效建议")

        # 4. 校验并还原候选编号 -> 真实院校名（不可虚构）
        cand_by_idx = {i + 1: c for i, c in enumerate(candidates)}
        clean_advice: list[dict[str, Any]] = []
        for a in advice:
            try:
                order = int(a.get("order", 0))
            except (TypeError, ValueError):
                order = 0
            sidx_raw = a.get("suggest_index")
            suggest_college = None
            try:
                sidx = int(sidx_raw) if sidx_raw not in (None, "", 0) else None
            except (TypeError, ValueError):
                sidx = None
            if sidx and sidx in cand_by_idx:
                c = cand_by_idx[sidx]
                suggest_college = f"{c['college']['name']} 组{c['group_code']}（{c['group_prob']:.0%}）"
            elif a.get("action") == "swap":
                continue  # swap 但给了无效编号 —— 丢弃防虚构
            clean_advice.append({
                "order": order,
                "college_name": slots[order - 1]["college_name"] if 0 < order <= len(slots) else "?",
                "action": a.get("action", "keep"),
                "suggest_college": suggest_college,
                "reason": a.get("reason", ""),
            })

        return {
            "plan_id": plan_id,
            "summary": parsed.get("summary", ""),
            "advice": clean_advice,
            "message": f"AI 优化建议已生成，共点评 {len(clean_advice)} 个志愿",
            "reference": False,
        }

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 服务繁忙，请稍后再试")
    except Exception as e:
        detail = "AI 服务繁忙，请稍后再试"
        if "格式错误" in str(e) or "有效建议" in str(e):
            detail = f"AI 优化建议失败: {str(e)}"
        raise HTTPException(status_code=500, detail=detail)


@router.post("/volunteer/plan/{plan_id}/clone")
async def clone_plan(plan_id: str, body: ClonePlanRequest):
    from deeptutor.services.custom.volunteer_table_dao import clone_plan as dao_clone
    from deeptutor.services.custom.volunteer_table_dao import find_duplicate, get_plan

    source = get_plan(plan_id)
    if not source:
        raise HTTPException(status_code=404, detail="Plan not found")
    # 去重：内容与任一其他活跃方案完全一致则拒绝（保留顺序 + rank；源方案自身除外，
    # 因为"保存"即对当前方案做新快照）
    dup = find_duplicate(
        body.user_id, source["slots"],
        rank=source.get("rank"), exam_category=source.get("exam_category"),
    )
    if dup and dup["id"] != plan_id:
        raise HTTPException(
            status_code=409,
            detail=f"与志愿表{_plan_label(dup)}完全相同，未保存",
        )
    new_plan = dao_clone(plan_id, body.user_id, body.name)
    if not new_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return new_plan


@router.put("/volunteer/plan/{plan_id}/rename")
async def rename_plan(plan_id: str, body: ClonePlanRequest):
    from deeptutor.services.custom.volunteer_table_dao import rename_plan as dao_rename
    from deeptutor.services.custom.volunteer_table_dao import get_plan

    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    updated = dao_rename(plan_id, body.name or plan_id)
    return updated


@router.post("/volunteer/profile/validate")
async def validate_profile_endpoint(body: dict):
    from deeptutor.services.custom.student_profile import StudentProfile

    profile = StudentProfile.from_dict(body)
    return {"valid": len(profile.validate()) == 0, "errors": profile.validate()}


@router.get("/volunteer/plan/{plan_id}/diagnose")
async def diagnose_plan(plan_id: str):
    from deeptutor.services.custom.volunteer_table_dao import get_plan
    from deeptutor.services.custom.student_profile import StudentProfile
    from deeptutor.services.custom.volunteer_validator import validate_all
    from deeptutor.services.custom.college_dao import get_college_detail

    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    slots = plan["slots"]
    if not slots:
        return {"grade_score": 0, "risk_level": "高", "details": "志愿表为空"}

    # Build a basic profile from plan data for validation
    profile = StudentProfile(
        province=plan.get("province", "广东"),
        year=2026,
        exam_category=plan.get("exam_category", "物理"),
        rank=plan.get("rank"),
        medical_restrictions=plan.get("medical_restrictions") or [],
    )

    # Run conflict detection on all slots
    violations: list[dict] = []
    for s in slots:
        college = get_college_detail(s["college_id"]) or {}
        for m in s.get("majors", []):
            major_dict = {
                "id": m.get("major_id") or "",
                "name": m.get("major_name", ""),
                "medical_note": m.get("medical_note", ""),
            }
            vs = validate_all(profile, college, major_dict)
            for v in vs:
                v["college_name"] = s.get("college_name", "")
                v["major_name"] = m.get("major_name", "")
                violations.append(v)

    # Categorize by tier
    reach_slots = [s for s in slots if s["tier"] == "reach"]
    steady_slots = [s for s in slots if s["tier"] == "steady"]
    safe_slots = [s for s in slots if s["tier"] == "safe"]

    # 顺序志愿（单志愿）方案：不适用冲稳保梯度评分
    plan_batch = plan.get("batch", "")
    early_rule = EARLY_BATCH_RULES.get(plan_batch)
    if early_rule and not early_rule.get("parallel"):
        prob0 = slots[0].get("group_prob", slots[0].get("admission_prob", 0)) if slots else 0
        risk = "高" if prob0 < 0.35 else "中" if prob0 < 0.65 else "低"
        return {
            "grade_score": None,
            "risk_level": risk,
            "weakest_link_prob": prob0,
            "safe_slots_remaining": 0,
            "violations": violations,
            "details": {
                "mode": "顺序志愿",
                "note": "顺序志愿仅 1 个院校专业组志愿，不适用冲稳保梯度评分；须在公示合格名单/取得资格，对照招生章程报考",
                "has_all_tiers": False,
            },
        }

    # Grade scoring (0-100)
    score = 0

    # 1. Ratio check (30 pts)
    total = len(slots)
    has_all_tiers = len(reach_slots) > 0 and len(steady_slots) > 0 and len(safe_slots) > 0
    if has_all_tiers:
        score += 30
    elif len(reach_slots) > 0 and len(safe_slots) > 0:
        score += 20
    else:
        score += 10

    # 2. Trend check (30 pts) — prob should generally increase (safe > steady > reach)
    trend_ok = True
    for s in slots:
        for s2 in slots:
            p = s.get("group_prob", s.get("admission_prob", 0))
            p2 = s2.get("group_prob", s2.get("admission_prob", 0))
            if s["order"] < s2["order"] and p > p2:
                trend_ok = False
    if trend_ok:
        score += 30
    else:
        inversions = 0
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                pi = slots[i].get("group_prob", slots[i].get("admission_prob", 0))
                pj = slots[j].get("group_prob", slots[j].get("admission_prob", 0))
                if pi > pj:
                    inversions += 1
        if inversions <= len(slots) // 2:
            score += 20
        else:
            score += 10

    # 3. No inversions (20 pts)
    if trend_ok:
        score += 20
    else:
        score += 5

    # 4. Coverage (20 pts)
    if has_all_tiers:
        score += 20
    elif len(reach_slots) > 0 or len(safe_slots) > 0:
        score += 10

    # Risk analysis
    weakest_safe = min(safe_slots, key=lambda s: s.get("group_prob", s.get("admission_prob", 0))) if safe_slots else None
    weakest_prob = weakest_safe.get("group_prob", weakest_safe.get("admission_prob", 0)) if weakest_safe else 0

    if weakest_prob >= 0.8:
        risk_level = "低"
    elif weakest_prob >= 0.5:
        risk_level = "中"
    else:
        risk_level = "高"

    return {
        "grade_score": min(score, 100),
        "risk_level": risk_level,
        "weakest_link_prob": weakest_prob,
        "safe_slots_remaining": len(safe_slots),
        "violations": violations,
        "details": {
            "reach_count": len(reach_slots),
            "steady_count": len(steady_slots),
            "safe_count": len(safe_slots),
            "has_all_tiers": has_all_tiers,
            "trend_ok": trend_ok,
        },
    }


@router.get("/volunteer/plan/{plan_id}/export-pdf")
async def export_plan_pdf_endpoint(plan_id: str):
    try:
        from deeptutor.services.custom.export_service import export_plan_pdf as do_export

        pdf_bytes = do_export(plan_id)
        return Response(content=pdf_bytes, media_type="application/pdf", headers={
            "Content-Disposition": f"attachment; filename=volunteer_plan_{plan_id[:8]}.pdf",
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/volunteer/plan/{plan_id}/export-excel")
async def export_plan_excel_endpoint(plan_id: str):
    try:
        from deeptutor.services.custom.export_service import export_plan_excel as do_export

        xlsx_bytes = do_export(plan_id)
        return Response(content=xlsx_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
            "Content-Disposition": f"attachment; filename=volunteer_plan_{plan_id[:8]}.xlsx",
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
