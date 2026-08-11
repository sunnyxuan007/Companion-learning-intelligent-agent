from __future__ import annotations

import asyncio
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
    ids = [
        r["college_id"]
        for r in conn.execute(
            "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ?",
            (plan["province"], plan["exam_category"]),
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
