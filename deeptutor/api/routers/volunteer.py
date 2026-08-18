from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.services.custom.user_settings_dao import (
    get_user_weights,
    reset_user_weights,
    set_user_weights,
)

router = APIRouter()


def _resolve_strategies(strategies: list[str] | None, strategy: str | None) -> list[str]:
    if strategies:
        return strategies
    if strategy:
        return [strategy]
    return ["default"]


class WeightsResponse(BaseModel):
    weights: dict[str, float]
    default_weights: dict[str, float]
    auto_tuned: bool = False


class WeightsUpdateRequest(BaseModel):
    user_id: str = "default"
    weights: dict[str, float] = Field(..., description="Weight values that sum to 1.0")


@router.get("/volunteer/weights/{user_id}", response_model=WeightsResponse)
async def get_weights(user_id: str = "default"):
    from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS

    weights = get_user_weights(user_id)
    return WeightsResponse(weights=weights, default_weights=dict(VOLUNTEER_DEFAULT_WEIGHTS))


@router.post(
    "/volunteer/weights/auto-tune/{user_id}",
    response_model=WeightsResponse,
)
async def auto_tune_weights(user_id: str = "default"):
    from deeptutor.services.custom.adaptive_weights import compute_adaptive_weights
    from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS

    adapted = compute_adaptive_weights(user_id, dict(VOLUNTEER_DEFAULT_WEIGHTS))
    set_user_weights(user_id, adapted)
    return WeightsResponse(
        weights=adapted,
        default_weights=dict(VOLUNTEER_DEFAULT_WEIGHTS),
        auto_tuned=True,
    )


@router.put("/volunteer/weights/{user_id}", response_model=WeightsResponse)
async def update_weights(user_id: str, body: WeightsUpdateRequest):
    from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS

    new_weights = body.weights
    total = sum(new_weights.values())
    if abs(total - 1.0) > 0.01:
        raise HTTPException(
            status_code=400,
            content={"message": f"Weights must sum to 1.0, got {total:.2f}"},
        )

    current = get_user_weights(user_id)
    current.update(new_weights)
    set_user_weights(user_id, current)
    return WeightsResponse(
        weights=current,
        default_weights=dict(VOLUNTEER_DEFAULT_WEIGHTS),
        auto_tuned=False,
    )


@router.delete("/volunteer/weights/{user_id}", response_model=WeightsResponse)
async def reset_weights(user_id: str = "default"):
    from deeptutor.services.custom.models import VOLUNTEER_DEFAULT_WEIGHTS

    weights = reset_user_weights(user_id)
    return WeightsResponse(
        weights=weights,
        default_weights=dict(VOLUNTEER_DEFAULT_WEIGHTS),
        auto_tuned=False,
    )


class RecommendResponse(BaseModel):
    tiers: dict[str, list[dict]]
    total_count: int
    violations: list[dict] = []


class RecommendRequest(BaseModel):
    admission_province: str | None = "广东"
    college_province: str | None = None
    exam_category: str | None = None
    user_rank: int | None = None
    score: int | None = None
    level: str | None = None
    major_keyword: str | None = None
    major_categories: list[str] | None = None
    limit: int = 10
    user_id: str = "default"
    elective_subjects: list[str] | None = None
    bonus_points: int = 0
    medical_restrictions: list[str] | None = None
    gender: str | None = None
    year: int = 2026
    strategies: list[str] | None = None
    strategy: str | None = None  # deprecated, use strategies
    city_tier: str | None = None
    region: str | None = None
    cities: list[str] | None = None
    batch: str = "本科批"


@router.post("/volunteer/recommend", response_model=RecommendResponse)
async def recommend(body: RecommendRequest):
    from deeptutor.services.custom.college_dao import search_colleges
    from deeptutor.services.custom.volunteer_scorer import generate_recommendations
    from deeptutor.services.custom.student_profile import StudentProfile
    from deeptutor.services.custom.volunteer_validator import validate_all
    from deeptutor.services.custom.db import get_connection

    # Build StudentProfile
    profile = StudentProfile(
        province=body.admission_province or "广东",
        year=body.year,
        exam_category=body.exam_category or "",
        elective_subjects=body.elective_subjects or [],
        score=body.score,
        rank=body.user_rank,
        bonus_points=body.bonus_points,
        medical_restrictions=body.medical_restrictions or [],
        gender=body.gender,
        preferences={"level": body.level, "major_keyword": body.major_keyword},
    )

    errs = profile.validate()
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    profile_dict = profile.to_dict()
    if body.user_id:
        profile_dict["user_id"] = body.user_id

    # Get college_ids that have admission records for the user's province + exam_category
    if profile.exam_category and profile.province:
        conn = get_connection()
        ids = [
            r["college_id"]
            for r in conn.execute(
                "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ? AND (year < 2026 OR batch = ?)",
                (profile.province, profile.exam_category, body.batch),
            ).fetchall()
        ]
        conn.close()
    else:
        ids = None

    effective_strategies = _resolve_strategies(body.strategies, body.strategy)

    colleges = search_colleges(
        province=body.college_province,
        level=body.level,
        college_ids=ids,
        city_tier=body.city_tier,
        region=body.region,
        cities=body.cities,
        limit=2000,
    )
    if not colleges:
        return RecommendResponse(tiers={"reach": [], "steady": [], "safe": []}, total_count=0)

    # Run validation on all colleges
    all_violations: list[dict] = []
    for c in colleges:
        vs = validate_all(profile, c)
        all_violations.extend(vs)

    weights = get_user_weights(body.user_id)
    result = generate_recommendations(colleges, user_profile=profile_dict, weights=weights, top_n=body.limit, strategy=effective_strategies)

    tiers_out: dict[str, list[dict]] = {}
    for tier_key in ("reach", "steady", "safe"):
        items = result["tiers"].get(tier_key, [])
        tiers_out[tier_key] = [
            {
                "college_id": i["college"]["id"],
                "college_name": i["college"]["name"],
                "college_level": i["college"].get("level", ""),
                "college_province": i["college"].get("province", ""),
                "college_city": i["college"].get("city", ""),
                "total_score": i["total_score"],
                "detail_scores": i.get("detail_scores", {}),
                "explanations": i.get("explanations", {}),
                "evidence": i.get("evidence", {}),
            }
            for i in items
        ]

    total = sum(len(v) for v in tiers_out.values())
    return RecommendResponse(tiers=tiers_out, total_count=total, violations=all_violations[:20])


PER_TIER_CAPS_DEFAULT = {"reach": 50, "steady": 100, "safe": 80}


class BrowseRequest(BaseModel):
    admission_province: str = "广东"
    exam_category: str = "物理"
    user_rank: int | None = None
    score: int | None = None
    level: str | None = None
    strategies: list[str] | None = None
    strategy: str | None = None  # deprecated, use strategies
    major_categories: list[str] | None = None
    score_min: int | None = None
    score_max: int | None = None
    city_tier: str | None = None
    region: str | None = None
    cities: list[str] | None = None
    batch: str = "本科批"


@router.post("/volunteer/browse", response_model=RecommendResponse)
async def browse_recommendations(body: BrowseRequest):
    from deeptutor.services.custom.college_dao import search_colleges
    from deeptutor.services.custom.volunteer_scorer import generate_group_recommendations
    from deeptutor.services.custom.db import get_connection
    from deeptutor.services.custom.user_settings_dao import get_user_weights

    conn = get_connection()
    ids = [
        r["college_id"]
        for r in conn.execute(
            "SELECT DISTINCT college_id FROM admission_ranks WHERE province = ? AND exam_category = ? AND (year < 2026 OR batch = ?)",
            (body.admission_province, body.exam_category, body.batch),
        ).fetchall()
    ]
    conn.close()

    effective_strategies = _resolve_strategies(body.strategies, body.strategy)

    colleges = search_colleges(
        college_ids=ids, limit=5000,
        city_tier=body.city_tier, region=body.region, cities=body.cities,
    )
    if not colleges:
        return RecommendResponse(tiers={"reach": [], "steady": [], "safe": []}, total_count=0)
    colleges_map = {c["id"]: c for c in colleges}

    # Convert score→rank if rank not provided
    effective_rank = body.user_rank
    if not effective_rank and body.score:
        from deeptutor.services.custom.admission_dao import score_to_rank
        effective_rank = score_to_rank(body.admission_province, 2025, body.exam_category, body.score)

    profile = {
        "rank": effective_rank or 0,
        "province": body.admission_province,
        "exam_category": body.exam_category,
        "score": body.score,
    }

    # Build score_rank_range if score_min/score_max provided
    score_rank_range = None
    if body.score_min is not None and body.score_max is not None and body.admission_province:
        from deeptutor.services.custom.admission_dao import score_to_rank
        rank_low = score_to_rank(body.admission_province, 2025, body.exam_category, max(0, body.score_min))
        rank_high = score_to_rank(body.admission_province, 2025, body.exam_category, min(750, body.score_max))
        if rank_low > 0 and rank_high > 0:
            score_rank_range = (min(rank_low, rank_high), max(rank_low, rank_high))

    weights = get_user_weights("default")
    result = generate_group_recommendations(
        colleges_map,
        province=body.admission_province,
        exam_category=body.exam_category,
        user_profile=profile,
        weights=weights,
        top_n=9999,
        strategy=effective_strategies,
        major_categories=body.major_categories,
        per_tier_caps=PER_TIER_CAPS_DEFAULT,
        score_rank_range=score_rank_range,
        batch=body.batch,
    )

    # 广东招生代码（按省份）：official_code -> province_code
    province_codes: dict[str, str] = {}
    if body.admission_province:
        conn2 = get_connection()
        rows = conn2.execute(
            "SELECT official_code, province_code FROM college_code_map WHERE province = ?",
            (body.admission_province,),
        ).fetchall()
        conn2.close()
        for r in rows:
            province_codes.setdefault(r["official_code"], r["province_code"])

    import re as _re

    def _lookup_province_code(college_id: str) -> str | None:
        if not college_id:
            return None
        if college_id in province_codes:
            return province_codes[college_id]
        base = _re.sub(r"-[A-Za-z0-9]+$", "", college_id)
        return province_codes.get(base)

    tiers_out: dict[str, list[dict]] = {}
    for tier_key in ("reach", "steady", "safe"):
        items = result["tiers"].get(tier_key, [])
        tiers_out[tier_key] = [
            {
                "college_id": g["college"]["id"],
                "college_name": g["college"]["name"],
                "college_level": g["college"].get("level", ""),
                "college_province": g["college"].get("province", ""),
                "college_city": g["college"].get("city", ""),
                "province_code": _lookup_province_code(g["college"]["id"]),
                "group_code": g.get("group_code", ""),
                "group_prob": g.get("group_prob", 0.5),
                "rank_source": g.get("rank_source", "official"),
                "total_score": g.get("total_score", 0),
                "detail_scores": g.get("detail_scores", {}),
                "bargain_score": g.get("bargain_score", 0),
                "majors": g.get("majors", []),
            }
            for g in items
        ]

    total = sum(len(v) for v in tiers_out.values())
    return RecommendResponse(tiers=tiers_out, total_count=total)


class AdmissionHistoryItem(BaseModel):
    year: int
    min_rank: int
    min_score: float
    batch: str | None = None


@router.get("/volunteer/admission-history/{college_id}")
async def get_admission_history(
    college_id: str,
    province: str = "广东",
    exam_category: str = "物理",
    years: str = "2025,2024,2026",
):
    from deeptutor.services.custom.admission_dao import get_admission_ranks_by_college

    year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
    rows = get_admission_ranks_by_college(college_id, province, years=year_list, exam_category=exam_category)
    return [
        AdmissionHistoryItem(
            year=int(r["year"]),
            min_rank=int(r["min_rank"]),
            min_score=float(r["min_score"]),
            batch=r.get("batch"),
        )
        for r in rows
    ]


class StudySummaryItem(BaseModel):
    subject: str
    count: int
    avg_accuracy: float | None


@router.get("/study/summary/{user_id}")
async def get_study_summary(user_id: str = "default"):
    from deeptutor.services.custom.study_dao import get_subject_summary

    rows = get_subject_summary(user_id)
    return [StudySummaryItem(**r) for r in rows]


class GapAnalysisResponse(BaseModel):
    total_records: int
    weak_points_ranked: list[dict]
    strong_points_ranked: list[dict]
    suggestion: str


@router.get("/study/gap/{user_id}", response_model=GapAnalysisResponse)
async def get_gap_analysis(user_id: str = "default"):
    from deeptutor.services.custom.study_dao import get_gap_analysis

    return get_gap_analysis(user_id)


class RankConvertRequest(BaseModel):
    score: int | None = None
    rank: int | None = None
    from_year: int
    to_year: int
    exam_category: str
    province: str = "广东"


class RankConvertResponse(BaseModel):
    input_rank: int | None
    input_score: float | None
    output_rank: int
    output_score: float
    total_candidates: int


@router.get("/volunteer/medical-restrictions")
async def get_medical_restrictions():
    from deeptutor.services.custom.student_profile import MEDICAL_RESTRICTION_MAP
    return [{"code": k, "description": v} for k, v in MEDICAL_RESTRICTION_MAP.items()]


@router.post("/volunteer/profile/validate")
async def validate_profile(body: RecommendRequest):
    from deeptutor.services.custom.student_profile import StudentProfile
    profile = StudentProfile(
        province=body.admission_province or "广东",
        year=body.year,
        exam_category=body.exam_category or "",
        elective_subjects=body.elective_subjects or [],
        score=body.score,
        rank=body.user_rank,
        bonus_points=body.bonus_points,
        medical_restrictions=body.medical_restrictions or [],
        gender=body.gender,
    )
    return {"valid": len(profile.validate()) == 0, "errors": profile.validate()}


@router.post("/study/rank-convert", response_model=RankConvertResponse)
async def rank_convert(body: RankConvertRequest):
    from deeptutor.services.custom.admission_dao import (
        get_total_candidates,
        rank_to_score,
        score_to_rank,
    )

    if not body.rank and not body.score:
        raise HTTPException(status_code=400, detail="Must provide either score or rank")

    # Convert to rank first
    if body.rank:
        input_rank = body.rank
        input_score = rank_to_score(body.province, body.from_year, body.exam_category, body.rank)
    else:
        input_score = body.score
        input_rank = score_to_rank(body.province, body.from_year, body.exam_category, body.score)
        if not input_rank:
            raise HTTPException(status_code=400, detail="Cannot convert score to rank: no data for from_year")

    # Convert rank to target year
    output_score = rank_to_score(body.province, body.to_year, body.exam_category, input_rank)
    output_rank = score_to_rank(body.province, body.to_year, body.exam_category, output_score) if output_score else 0
    total = get_total_candidates(body.province, body.to_year, body.exam_category)

    return RankConvertResponse(
        input_rank=input_rank,
        input_score=input_score,
        output_rank=output_rank,
        output_score=output_score,
        total_candidates=total,
    )


class SubjectMatchRequest(BaseModel):
    exam_category: str
    elective_subjects: list[str] = []
    keyword: str | None = None


class SubjectMatchItem(BaseModel):
    major_id: str
    major_name: str
    category: str | None
    description: str | None


@router.post("/volunteer/subject-match")
async def subject_match(body: SubjectMatchRequest):
    from deeptutor.services.custom.major_dao import get_majors_by_subject, search_majors

    majors = get_majors_by_subject(body.exam_category)
    if body.keyword:
        majors = [m for m in majors if body.keyword.lower() in m["name"].lower()]
    return [SubjectMatchItem(major_id=m["id"], major_name=m["name"], category=m.get("category"), description=m.get("description")) for m in majors]


class FavoriteRequest(BaseModel):
    user_id: str = "default"
    item_type: str
    item_id: str


@router.post("/volunteer/favorite")
async def add_favorite(body: FavoriteRequest):
    from deeptutor.services.custom.user_favorites_dao import add_favorite
    ok = add_favorite(body.user_id, body.item_type, body.item_id)
    return {"ok": ok}


@router.delete("/volunteer/favorite")
async def remove_favorite(body: FavoriteRequest):
    from deeptutor.services.custom.user_favorites_dao import remove_favorite
    ok = remove_favorite(body.user_id, body.item_type, body.item_id)
    return {"ok": ok}


@router.get("/volunteer/favorites/{user_id}")
async def list_favorites(user_id: str = "default", item_type: str | None = None):
    from deeptutor.services.custom.user_favorites_dao import get_favorites
    return get_favorites(user_id, item_type)


@router.get("/volunteer/browsing-history/{user_id}")
async def browsing_history(user_id: str = "default"):
    from deeptutor.services.custom.user_favorites_dao import get_browsing_history
    return get_browsing_history(user_id)


@router.get("/volunteer/holland/questions")
async def holland_questions():
    from deeptutor.services.custom.holland_assessment import DISCLAIMER, QUESTIONS
    return {"questions": QUESTIONS, "disclaimer": DISCLAIMER}


@router.post("/volunteer/holland/assess")
async def holland_assess(body: dict):
    from deeptutor.services.custom.holland_assessment import get_major_recommendations, save_assessment

    user_id = body.get("user_id", "default")
    scores = body.get("scores", {})
    result = save_assessment(user_id, scores)
    recommendations = get_major_recommendations(result["top3"])
    return {"result": result, "major_recommendations": recommendations}


@router.get("/volunteer/major-categories")
async def list_major_categories():
    from deeptutor.services.custom.db import get_connection
    conn = get_connection()
    cats = [r["category"] for r in conn.execute(
        "SELECT DISTINCT category FROM majors WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()]
    conn.close()
    return {"categories": cats}


MUNICIPALITIES = {"北京", "上海", "天津", "重庆"}


@router.get("/volunteer/cities")
async def list_cities(region: str | None = None):
    from deeptutor.services.custom.db import get_connection
    conn = get_connection()
    # 直辖市（北京/上海/天津/重庆）的 colleges.city 存的是区名，统一折叠为市名
    sql = (
        "SELECT DISTINCT RTRIM(city, '市') AS city, province, region FROM colleges"
        " WHERE city IS NOT NULL AND city != ''"
    )
    params: list[str] = []
    if region:
        sql += " AND region=?"
        params.append(region)
    sql += " ORDER BY region, city"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()

    seen: dict[tuple[str, str], dict] = {}
    for r in rows:
        prov = r["province"] or ""
        label = prov if prov in MUNICIPALITIES else r["city"]
        key = (prov, label)
        if key not in seen:
            seen[key] = {"city": label, "province": prov, "region": r.get("region")}
    return {"cities": list(seen.values())}


@router.get("/volunteer/score-distribution")
async def score_distribution(province: str = "广东", exam_category: str = "物理"):
    from deeptutor.services.custom.db import get_connection
    conn = get_connection()
    rows = conn.execute(
        """SELECT CAST(min_score/10 AS INTEGER)*10 AS bucket,
                  COUNT(DISTINCT college_id||group_code) AS count
           FROM admission_ranks
           WHERE province=? AND exam_category=? AND min_score>0 AND group_code!=''
           GROUP BY CAST(min_score/10 AS INTEGER)*10
           ORDER BY bucket""",
        (province, exam_category),
    ).fetchall()
    conn.close()
    buckets = [{"score_low": r["bucket"], "score_high": r["bucket"] + 10, "count": r["count"]} for r in rows]
    return {"buckets": buckets, "total_groups": sum(r["count"] for r in rows)}


@router.get("/volunteer/holland/result/{user_id}")
async def holland_result(user_id: str = "default"):
    from deeptutor.services.custom.holland_assessment import get_assessment, get_major_recommendations

    result = get_assessment(user_id)
    if not result:
        return {"result": None}
    recommendations = get_major_recommendations(result["top3"])
    return {"result": result, "major_recommendations": recommendations}
