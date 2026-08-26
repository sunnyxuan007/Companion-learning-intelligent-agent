"""辅助学习 REST API —— 错题本 / AI 分析 / 学习者画像。

路径均挂 `/api/v1`（在 `deeptutor/api/main.py` 注册）。

与升学侧的衔接端点：
- `GET  /study/profile`              —— 学习者画像（含专业倾向）
- `GET  /study/profile/academic-inputs` —— 画像注入升学推荐的实际参数（_subjects/_learner_profile）
- `POST /study/profile/apply`        —— 画像应用到升学（写 user_settings + L3 记忆）

注意：`/study/mistakes/stats` 必须注册在 `/study/mistakes/{mistake_id}` 之前，
避免路径参数遮蔽（吸取 volunteer_table 的历史教训）。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from deeptutor.services.custom.mistake_dao import (
    add_review,
    create_mistake,
    delete_mistake,
    get_mistake,
    get_mistake_stats,
    list_mistakes,
    update_mistake,
)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    user_id: str = "default"
    subject: str = Field("", description="科目，如 数学/物理/英语")
    source_type: str = Field("mistake", description="mistake(错题)/paper(试卷)/homework(作业)")
    content: str = Field(..., min_length=1, description="错题/试卷/作业的文本内容")
    question_hint: str | None = None


class MistakeCreateRequest(BaseModel):
    user_id: str = "default"
    subject: str = ""
    source_type: str = "mistake"
    question: str = Field(..., description="题目")
    answer: str = ""
    explanation: str = ""
    knowledge_points: list[str] = []
    mistake_reason: str = ""
    difficulty: str = "medium"
    is_mistake: bool = True


class MistakeUpdateRequest(BaseModel):
    subject: str | None = None
    question: str | None = None
    answer: str | None = None
    explanation: str | None = None
    knowledge_points: list[str] | None = None
    mistake_reason: str | None = None
    difficulty: str | None = None
    status: str | None = None


class ReviewRequest(BaseModel):
    performance: bool = Field(..., description="本次复习是否做对")


# ── AI 分析 ──────────────────────────────────────────────


@router.post("/study/analyze")
async def analyze_content(body: AnalyzeRequest):
    """上传错题/试卷/作业文本，AI 分析并整理进错题本。"""
    from deeptutor.services.custom.ai_tutor_service import get_ai_tutor_service

    if not body.content.strip():
        raise HTTPException(status_code=400, content={"message": "内容不能为空"})
    service = get_ai_tutor_service()
    result = await service.analyze_content(
        body.user_id,
        subject=body.subject,
        source_type=body.source_type,
        content=body.content,
        question_hint=body.question_hint,
    )
    return result


@router.post("/study/upload")
async def upload_file(
    user_id: str = "default",
    subject: str = "",
    source_type: str = "mistake",
    file: UploadFile | None = File(None),
):
    """上传文件（.txt/.md/.csv 等文本格式）并触发 AI 分析。"""
    if file is None:
        raise HTTPException(status_code=400, content={"message": "未收到文件"})
    filename = (file.filename or "").lower()
    if not filename.endswith((".txt", ".md", ".csv", ".json", ".log")):
        raise HTTPException(
            status_code=400,
            content={"message": "暂不支持该文件类型，请上传 .txt/.md 文本文件（图片/PDF 的 OCR 解析即将支持）"},
        )
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("gbk", errors="replace")
    if not content.strip():
        raise HTTPException(status_code=400, content={"message": "文件内容为空"})

    from deeptutor.services.custom.ai_tutor_service import get_ai_tutor_service

    result = await get_ai_tutor_service().analyze_content(
        user_id, subject=subject, source_type=source_type, content=content[:6000]
    )
    return {"filename": file.filename, **result}


# ── 错题本 CRUD ──────────────────────────────────────────


@router.post("/study/mistakes")
async def create_mistake_api(body: MistakeCreateRequest):
    """手动保存一条错题（不经过 AI 分析）。"""
    item = create_mistake(
        body.user_id,
        source_type=body.source_type,
        subject=body.subject,
        question=body.question,
        ai_answer=body.answer,
        ai_explanation=body.explanation,
        knowledge_points=body.knowledge_points,
        mistake_reason=body.mistake_reason,
        difficulty=body.difficulty,
        is_mistake=body.is_mistake,
    )
    _refresh_profile(body.user_id)
    return item


@router.get("/study/mistakes")
async def list_mistakes_api(
    user_id: str = "default",
    subject: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    """错题本列表（默认最新在前）。"""
    return list_mistakes(
        user_id,
        subject=subject,
        status=status,
        source_type=source_type,
        limit=min(limit, 500),
        offset=offset,
    )


@router.get("/study/mistakes/stats")
async def mistakes_stats(user_id: str = "default"):
    """错题本统计：总量 / 按科目 / 按状态 / 按难度 / 薄弱知识点。"""
    return get_mistake_stats(user_id)


@router.get("/study/mistakes/{mistake_id}")
async def get_mistake_api(mistake_id: str):
    item = get_mistake(mistake_id)
    if item is None:
        raise HTTPException(status_code=404, content={"message": "错题不存在"})
    return item


@router.put("/study/mistakes/{mistake_id}")
async def update_mistake_api(mistake_id: str, body: MistakeUpdateRequest):
    item = get_mistake(mistake_id)
    if item is None:
        raise HTTPException(status_code=404, content={"message": "错题不存在"})
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = update_mistake(mistake_id, **fields)
    _refresh_profile(item.get("user_id", "default"))
    return updated


@router.delete("/study/mistakes/{mistake_id}")
async def delete_mistake_api(mistake_id: str):
    item = get_mistake(mistake_id)
    if item is None:
        raise HTTPException(status_code=404, content={"message": "错题不存在"})
    deleted = delete_mistake(mistake_id)
    if deleted:
        _refresh_profile(item.get("user_id", "default"))
    return {"deleted": deleted}


@router.post("/study/mistakes/{mistake_id}/review")
async def review_mistake_api(mistake_id: str, body: ReviewRequest):
    """复习打卡：performance=true 做对 / false 仍错，更新掌握度。"""
    item = get_mistake(mistake_id)
    if item is None:
        raise HTTPException(status_code=404, content={"message": "错题不存在"})
    updated = add_review(mistake_id, item.get("user_id", "default"), body.performance)
    _refresh_profile(item.get("user_id", "default"))
    return updated


# ── 学习者画像（升学衔接） ────────────────────────────────


@router.get("/study/profile")
async def learner_profile(user_id: str = "default"):
    """学习者画像：学科掌握度 / 薄弱知识点 / 专业倾向 / 画像摘要。"""
    from deeptutor.services.custom.learner_profile_service import compute_learner_profile

    return compute_learner_profile(user_id)


@router.get("/study/profile/majors")
async def profile_majors(user_id: str = "default", top_n: int = 10):
    """画像 → 适合专业倾向（升学侧专业推荐的画像维度）。"""
    from deeptutor.services.custom.learner_profile_service import recommend_majors_by_profile

    return {"majors": recommend_majors_by_profile(user_id, top_n=top_n)}


@router.get("/study/profile/academic-inputs")
async def academic_inputs(user_id: str = "default"):
    """返回画像注入升学推荐引擎的实际参数（_subjects / _learner_profile）。

    升学 browse/recommend 端点内部即使用此结构；此端点用于前端预览
    「学习画像如何影响志愿推荐」。
    """
    from deeptutor.services.custom.learner_profile_service import build_academic_fit_inputs

    return build_academic_fit_inputs(user_id)


@router.post("/study/profile/apply")
async def apply_profile(user_id: str = "default"):
    """把学习画像「应用到升学」：持久化 + 写 user_settings + 写回 L3 记忆。"""
    from deeptutor.services.custom.learner_profile_service import apply_profile_to_volunteer

    profile = await apply_profile_to_volunteer(user_id)
    return {"applied": True, "profile": profile}


def _refresh_profile(user_id: str) -> None:
    """错题本变化后刷新画像缓存（异常安全，不阻塞主请求）。"""
    try:
        from deeptutor.services.custom.learner_profile_service import save_profile

        save_profile(user_id)
    except Exception:
        pass
