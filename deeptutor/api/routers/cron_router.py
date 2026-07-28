from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.services.cron import CronOwner, CronSchedule, get_cron_service

router = APIRouter()


class CronScheduleRequest(BaseModel):
    kind: str = Field(..., description="'every' for periodic, 'cron' for cron expression")
    every_seconds: int | None = Field(None, ge=30, description="Interval in seconds (for 'every')")
    expr: str | None = Field(None, description="Cron expression (for 'cron'), e.g. '0 9 * * 1'")
    tz: str | None = "Asia/Shanghai"


class CreateCronJobRequest(BaseModel):
    session_id: str = Field(default="default", description="Session ID for the response to land in")
    user_id: str = "default"
    name: str = "定时学习分析"
    message: str = "分析我最近一周的学习薄弱点并给出针对性建议"
    schedule: CronScheduleRequest


class CronJobResponse(BaseModel):
    id: str
    name: str
    message: str
    schedule_kind: str
    next_run_at_ms: int | None
    enabled: bool


class CronJobListResponse(BaseModel):
    jobs: list[CronJobResponse]


@router.get("/cron/jobs", response_model=CronJobListResponse)
async def list_jobs(user_id: str = "default"):
    service = get_cron_service()
    jobs = service.list_jobs(owner_key=f"chat:{user_id}")
    return CronJobListResponse(
        jobs=[
            CronJobResponse(
                id=j.id,
                name=j.name,
                message=j.message,
                schedule_kind=j.schedule.kind,
                next_run_at_ms=j.state.next_run_at_ms,
                enabled=j.enabled,
            )
            for j in jobs
        ]
    )


@router.post("/cron/jobs", response_model=CronJobResponse)
async def create_job(body: CreateCronJobRequest):
    service = get_cron_service()
    try:
        schedule = CronSchedule(
            kind=body.schedule.kind,
            every_seconds=body.schedule.every_seconds,
            expr=body.schedule.expr,
            tz=body.schedule.tz,
        )
        owner = CronOwner(
            kind="chat",
            user_id=body.user_id,
            is_admin=False,
            session_id=body.session_id,
            language="zh",
        )
        job = service.add_job(
            name=body.name,
            message=body.message,
            schedule=schedule,
            owner=owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, content={"message": str(e)}) from e

    return CronJobResponse(
        id=job.id,
        name=job.name,
        message=job.message,
        schedule_kind=job.schedule.kind,
        next_run_at_ms=job.state.next_run_at_ms,
        enabled=job.enabled,
    )


@router.delete("/cron/jobs/{job_id}")
async def delete_job(job_id: str, user_id: str = "default"):
    service = get_cron_service()
    ok = service.cancel_job(job_id, owner_key=f"chat:{user_id}")
    if not ok:
        raise HTTPException(status_code=404, content={"message": "Job not found"})
    return {"status": "deleted"}
