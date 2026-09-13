from typing import Any

from app.db.models import Job
from app.db.session import SessionLocal
from app.jobs.manager import JobManager, job_manager
from app.professional import append_stage_trace
from fastapi import HTTPException


def job_view(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "checkpoint": job.checkpoint or {},
        "error": job.error,
    }


def friendly_job_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    text = str(exc).strip()
    if "timeout" in text.lower() or "timed out" in text.lower():
        return "模型服务响应超时，任务已安全停止，请稍后重试或减少单次页数"
    if "<!doctype html" in text.lower() or "<html" in text.lower():
        return "上游服务返回了网页错误，任务已安全停止，请稍后重试"
    return text[:500] or "后台生成失败，请稍后重试"


async def set_job_stage(
    job_id: str,
    progress: float,
    stage: str,
    label: str,
    manager: JobManager = job_manager,
) -> None:
    manager.ensure_active(job_id)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        checkpoint = append_stage_trace(job.checkpoint or {}, stage, label, progress)
        job.status = "running"
        job.progress = progress
        job.checkpoint = checkpoint
        db.commit()
        snapshot = job_view(job)
    await manager.publish(job_id, {**snapshot, "type": "progress"})
