"""Durable background job for "导出讲解视频" (narrated video export)."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ExportRecord, Job, Project
from app.db.session import SessionLocal
from app.delivery_media.ffmpeg import find_ffmpeg
from app.delivery_media.tts import resolve_speech_route
from app.delivery_media.video import build_narrated_video
from app.evaluation.fingerprints import export_source_fingerprint
from app.jobs.manager import JobCancelled, JobManager, job_manager
from app.jobs.progress import friendly_job_error, job_view, set_job_stage
from app.jobs.sqlite_writes import run_job_write_async
from app.professional import append_stage_trace
from app.slides import load_slides

VIDEO_JOB_KIND = "narrated-video"
VIDEO_FORMAT = "mp4"


class NarratedVideoRequest(BaseModel):
    locale: Literal["zh-CN", "en-US"] = "zh-CN"
    tts: bool = True
    subtitles: bool = True
    voice: str | None = Field(default=None, max_length=80)
    audio_format: Literal["mp3", "wav", "aac", "flac", "opus"] | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_job_checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": "queued",
        "label": "讲解视频任务已提交，正在排队",
        "workflow": {
            "version": "narrated-video-v1",
            "resumable": True,
            "payload": payload,
            "resumeCount": 0,
        },
    }


async def _finish(job_id: str, status: str, label: str, **fields: Any) -> dict | None:
    def write(db: Session) -> dict | None:
        job = db.get(Job, job_id)
        if not job:
            return None
        progress = 1.0 if status == "completed" else float(job.progress or 0)
        checkpoint = append_stage_trace(job.checkpoint or {}, status, label, progress)
        checkpoint.update(fields.get("checkpoint") or {})
        job.status = status
        job.progress = progress
        job.error = fields.get("error")
        job.checkpoint = checkpoint
        db.commit()
        return job_view(job)

    return await run_job_write_async(write)


def _register_export(project_id: str, target: Path, report: dict) -> str:
    with SessionLocal() as db:
        record = ExportRecord(
            project_id=project_id, format=VIDEO_FORMAT, artifact_path=str(target), report=report
        )
        db.add(record)
        db.commit()
        return record.id


async def run_video_job(
    job_id: str,
    project_id: str,
    payload: dict[str, Any] | None = None,
    manager: JobManager = job_manager,
) -> None:
    from app.api.delivery_routes import (
        ensure_current_preview,
        immutable_export_path,
        publish_latest_export,
    )

    options = NarratedVideoRequest.model_validate(payload or {})
    work_dir: Path | None = None
    try:
        await set_job_stage(job_id, 0.05, "preparing", "正在检查页面与讲解文本", manager)
        with SessionLocal() as db:
            project = db.get(Project, project_id)
            if not project:
                raise RuntimeError("项目不存在或已删除")
            slides = load_slides(project_id, db)
            ensure_current_preview(project, slides)
            route = resolve_speech_route(db, options.voice, options.audio_format) if options.tts else None
            target = immutable_export_path(project, VIDEO_FORMAT)
            project_root = Path(project.artifact_path)
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("未找到 ffmpeg；请安装 ffmpeg 或设置 YINGZHANG_FFMPEG 后重试")
        work_dir = project_root / "exports" / "video-work" / job_id
        if work_dir.exists():
            shutil.rmtree(work_dir)
        total = max(1, len(slides))

        async def progress(index: int, _total: int, label: str) -> None:
            await set_job_stage(
                job_id, round(0.1 + 0.8 * (index - 1) / total, 3), "rendering_video", label, manager
            )

        build = await build_narrated_video(
            slides,
            project_root / "slides" / "rendered" / "slides",
            work_dir,
            target,
            ffmpeg=ffmpeg,
            synthesize=route.synthesize if route else None,
            audio_format=route.audio_format if route else "mp3",
            locale=options.locale,
            subtitles=options.subtitles,
            on_progress=progress,
        )
        manager.ensure_active(job_id)
        await set_job_stage(job_id, 0.95, "registering", "正在登记导出文件", manager)
        latest = project_root / "exports" / "presentation.mp4"
        publish_latest_export(target, latest)
        if build.subtitles:
            publish_latest_export(build.subtitles, latest.with_suffix(".srt"))
        report = {
            "sourceFingerprint": export_source_fingerprint(slides),
            "deliveryStage": "draft",
            "artifactSha256": _sha256(target),
            "locale": options.locale,
            "tts": {
                "status": "synthesized" if route else ("not-configured" if options.tts else "disabled"),
                "model": route.model if route else None,
                "provider": route.provider if route else None,
                "voice": route.voice if route else None,
            },
            **build.report(),
        }
        export_id = _register_export(project_id, target, report)
        snapshot = await _finish(
            job_id,
            "completed",
            "讲解视频已生成",
            checkpoint={"result": {
                "exportId": export_id,
                "video": str(target),
                "subtitles": str(build.subtitles) if build.subtitles else None,
                "durationSeconds": report["durationSeconds"],
                "ttsSlides": report["ttsSlides"],
                "silentSlides": report["silentSlides"],
                "download": f"/api/v1/projects/{project_id}/export/video",
            }},
        )
        if snapshot:
            await manager.publish(job_id, {**snapshot, "type": "completed"})
    except JobCancelled as exc:
        snapshot = await _finish(job_id, "cancelled", str(exc))
        if snapshot:
            await manager.publish(job_id, {**snapshot, "type": "cancelled"})
    except Exception as exc:  # noqa: BLE001 - job boundary persists every failure
        detail = getattr(exc, "detail", None)
        message = (
            str(detail.get("message")) if isinstance(detail, dict) and detail.get("message")
            else friendly_job_error(exc)
        )
        snapshot = await _finish(job_id, "failed", message, error=message)
        if snapshot:
            await manager.publish(job_id, {**snapshot, "type": "failed"})
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)


def new_video_job(project_id: str, payload: dict[str, Any]) -> Job:
    return Job(
        id=str(uuid.uuid4()),
        project_id=project_id,
        kind=VIDEO_JOB_KIND,
        status="queued",
        progress=0.0,
        checkpoint=video_job_checkpoint(payload),
    )


def _resume_video_job(snapshot: dict):
    workflow = (snapshot.get("checkpoint") or {}).get("workflow") or {}
    return run_video_job(snapshot["id"], snapshot["project_id"], workflow.get("payload") or {})


job_manager.register_runner(lambda kind: kind == VIDEO_JOB_KIND, _resume_video_job)
