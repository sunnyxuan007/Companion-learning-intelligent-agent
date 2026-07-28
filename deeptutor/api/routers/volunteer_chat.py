from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.services.custom.volunteer_chat_service import get_chat_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    context: dict[str, Any] | None = None
    learner_profile: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("/volunteer/chat", response_model=ChatResponse)
async def volunteer_chat(body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    service = get_chat_service()
    result = await service.chat(
        message=body.message.strip(),
        session_id=body.session_id,
        context=body.context,
        learner_profile=body.learner_profile,
    )
    return ChatResponse(reply=result["reply"], session_id=result["session_id"])


@router.post("/volunteer/chat/reset")
async def reset_chat(session_id: str):
    service = get_chat_service()
    service.reset_session(session_id)
    return {"ok": True}
