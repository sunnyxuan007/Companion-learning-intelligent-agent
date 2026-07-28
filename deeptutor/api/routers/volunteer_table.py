from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()

PROVINCE_RULES: dict[str, dict[str, Any]] = {
    "江苏": {"groups": 40, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "浙江": {"groups": 80, "mode": "专业", "ratio": [3, 4, 3]},
    "广东": {"groups": 45, "mode": "院校专业组", "ratio": [3, 4, 3]},
    "北京": {"groups": 30, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "上海": {"groups": 24, "mode": "院校专业组", "ratio": [3, 3, 4]},
    "default": {"groups": 30, "mode": "院校", "ratio": [3, 3, 4]},
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


class CreatePlanRequest(BaseModel):
    user_id: str = "default"
    province: str = "广东"
    exam_category: str = "物理"
    rank: int
    score: int | None = None
    level: str | None = None
    strategies: list[str] | None = None
    strategy: str | None = None  # deprecated, use strategies
    major_categories: list[str] | None = None
    score_rank_range: tuple[int, int] | None = None
    city_tier: str | None = None
    region: str | None = None
    cities: list[str] | None = None


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

    conn = get_connection()
    ids = [
        r["college_id"]
        for r in conn.execute(
            "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ?",
            (body.province, body.exam_category),
        ).fetchall()
    ]
    conn.close()

    from deeptutor.api.routers.volunteer import _resolve_strategies
    effective_strategies = _resolve_strategies(body.strategies, body.strategy)

    colleges = search_colleges(
        college_ids=ids, limit=2000,
        city_tier=body.city_tier, region=body.region, cities=body.cities,
    )
    if not colleges:
        raise HTTPException(status_code=400, detail="No colleges found for given province")

    colleges_map = {c["id"]: c for c in colleges}

    profile = {
        "rank": body.rank,
        "province": body.province,
        "exam_category": body.exam_category,
        "user_id": body.user_id,
    }
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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成推荐失败: {str(e)}")

    rules = PROVINCE_RULES.get(body.province, PROVINCE_RULES["default"])
    ratio = rules["ratio"]
    total_groups = rules["groups"]

    reach_pool = rec_result["tiers"].get("reach", [])
    steady_pool = rec_result["tiers"].get("steady", [])
    safe_pool = rec_result["tiers"].get("safe", [])

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
            if prob >= 0.8:
                safe_pool.insert(safe_count, item)
                safe_count += 1
            elif prob >= 0.45:
                steady_pool.insert(steady_count, item)
                steady_count += 1
            else:
                reach_pool.insert(reach_count, item)
                reach_count += 1

    # Look up major names
    conn = get_connection()
    major_names = {
        r["id"]: r["name"]
        for r in conn.execute("SELECT id, name FROM majors").fetchall()
    }
    conn.close()

    slots: list[dict[str, Any]] = []
    order = 1
    for pool, tier, count in [
        (reach_pool, "reach", reach_count),
        (steady_pool, "steady", steady_count),
        (safe_pool, "safe", safe_count),
    ]:
        for item in pool[:count]:
            college = item["college"]
            majors = []
            for m in item["majors"]:
                mid = m["major_id"]
                majors.append({
                    "major_id": mid,
                    "major_name": major_names.get(mid, mid),
                    "admission_prob": m["admission_prob"],
                    "order": len(majors) + 1,
                    "tag": m.get("tag", "可选"),
                })

            slots.append({
                "college_id": college["id"],
                "college_name": college["name"],
                "group_code": item["group_code"],
                "group_name": f"{item['group_code']}组",
                "group_prob": item["group_prob"],
                "tier": tier,
                "order": order,
                "adjustable": True,
                "reason": f"{'冲刺' if tier == 'reach' else '稳妥' if tier == 'steady' else '保底'}志愿推荐",
                "majors": majors,
                "bargain_score": item.get("bargain_score", 0),
            })
            order += 1

    plan = dao_create(body.user_id, body.province, body.exam_category, body.rank, rules, slots)
    return plan


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
    from deeptutor.services.custom.volunteer_table_dao import delete_plan as dao_delete

    if not dao_delete(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True}


@router.get("/volunteer/plan/list")
async def list_plans(user_id: str = "default"):
    from deeptutor.services.custom.volunteer_table_dao import list_plans as dao_list

    return {"plans": dao_list(user_id)}


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
    from deeptutor.services.custom.volunteer_table_dao import get_plan, update_plan
    from deeptutor.services.custom.college_dao import search_colleges
    from deeptutor.services.custom.volunteer_scorer import generate_recommendations
    from deeptutor.services.llm import complete

    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    slots = plan["slots"]
    if not slots:
        raise HTTPException(status_code=400, detail="志愿表为空")

    # Get eligible colleges
    from deeptutor.services.custom.db import get_connection as db_conn

    conn = db_conn()
    ids = [
        r["college_id"]
        for r in conn.execute(
            "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ?",
            (plan["province"], plan["exam_category"]),
        ).fetchall()
    ]
    conn.close()

    college_pool = search_colleges(college_ids=ids, limit=500)
    pool_names = {c["id"]: c["name"] for c in college_pool}

    # Build context for LLM
    slot_info = []
    for s in slots:
        slot_info.append(f"#{s['order']} {s['college_name']} ({s['tier']}, 概率 {s.get('group_prob', s.get('admission_prob', 0)):.0%})")
    slot_text = "\n".join(slot_info)
    college_names = "\n".join(f"{pool_names[k]}" for k in list(pool_names.keys())[:50]) + f"\n...等共 {len(pool_names)} 所院校"

    prompt = (
        f"你是高考志愿填报专家。当前志愿表方案如下（省份：{plan['province']}，科类：{plan['exam_category']}，位次：{plan['rank']}）：\n\n"
        f"当前志愿：\n{slot_text}\n\n"
        f"可选院校池（前50所）：\n{college_names}\n\n"
        "请优化这份志愿表，确保：\n"
        "1. 冲稳保梯度合理（冲刺<0.45，稳妥0.45-0.8，保底>0.8）\n"
        "2. 无倒序（录取概率应升序排列）\n"
        "3. 使用可选院校池中的院校，不得虚构\n"
        "4. 每档至少3个志愿\n\n"
        "以JSON格式输出优化后的志愿表，格式：{\"slots\": [{\"college_name\": \"...\", \"tier\": \"reach/steady/safe\", \"admission_prob\": 0.XX, \"reason\": \"...\"}]}"
    )

    try:
        reply = await complete(prompt=prompt, system_prompt="你是一个志愿填报专家，只输出JSON。", temperature=0.3, max_tokens=2048)
        # Extract JSON from reply
        import json
        import re

        json_match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not json_match:
            raise ValueError("LLM返回格式错误")

        parsed = json.loads(json_match.group())
        new_slots = parsed.get("slots", [])
        if not new_slots:
            raise ValueError("LLM未返回有效slots")

        # Validate: only use real colleges from pool
        valid_slots = []
        order = 1
        for s in new_slots:
            cid = None
            for pid, pname in pool_names.items():
                if s["college_name"] in pname or pname in s["college_name"]:
                    cid = pid
                    break
            if not cid:
                continue
            valid_slots.append({
                "college_id": cid,
                "college_name": s["college_name"],
                "major_id": "GEN",
                "group_code": "",
                "tier": s.get("tier", "steady"),
                "admission_prob": min(0.99, max(0.01, s.get("admission_prob", 0.5))),
                "order": order,
                "reason": s.get("reason", f"AI调整-{s.get('tier', '')}"),
            })
            order += 1

        if not valid_slots:
            raise ValueError("调整后无双表，LLM生成了虚构院校")

        updated = update_plan(plan_id, valid_slots)
        return {"plan": updated, "message": f"AI调整完成，共 {len(valid_slots)} 个志愿", "original_count": len(slots)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI调整失败: {str(e)}")


@router.post("/volunteer/plan/{plan_id}/clone")
async def clone_plan(plan_id: str, body: ClonePlanRequest):
    from deeptutor.services.custom.volunteer_table_dao import clone_plan as dao_clone

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
    )

    # Run conflict detection on all slots
    violations: list[dict] = []
    for s in slots:
        college = get_college_detail(s["college_id"]) or {}
        for m in s.get("majors", []):
            vs = validate_all(profile, college, None)
            for v in vs:
                v["college_name"] = s.get("college_name", "")
                v["major_name"] = m.get("major_name", "")
                violations.append(v)

    # Categorize by tier
    reach_slots = [s for s in slots if s["tier"] == "reach"]
    steady_slots = [s for s in slots if s["tier"] == "steady"]
    safe_slots = [s for s in slots if s["tier"] == "safe"]

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
