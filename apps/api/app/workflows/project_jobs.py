from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db.models import Job, Project
from app.db.session import SessionLocal
from app.jobs.manager import JobCancelled, JobManager, job_manager
from app.jobs.progress import friendly_job_error, job_view, set_job_stage
from app.presentation_engine.service import EngineError
from app.professional import append_stage_trace
from app.workflows.bounded import BoundedWorkflowRunner, NodeContract
from app.workflows.project import (
    ProjectActionInput,
    ProjectActionOutput,
    ProjectGateInput,
    ProjectGateOutput,
    expected_project_artifacts,
    gate_artifacts,
    project_node_name,
)
from fastapi import HTTPException
from sqlalchemy.orm import Session

JOB_LABELS = {
    "outline": ("正在读取材料并准备上下文", "正在调用模型规划叙事与页面大纲"),
    "sample": ("正在准备代表页面", "正在渲染封面、中间页和结尾页样张"),
    "generate": ("正在准备全部页面", "正在生成候选版式并进行视觉评分"),
    "full": ("正在读取材料并建立完整演示", "正在自动规划、生成并完成质量检查"),
}

PageObserver = Callable[[dict[str, Any]], Awaitable[None]]
CancellationCheck = Callable[[], bool]
PlanOperation = Callable[[str, dict[str, Any], Session], Awaitable[dict[str, Any]]]
SampleOperation = Callable[[str, Session], Awaitable[dict[str, Any]]]
GenerateOperation = Callable[
    [str, Session, PageObserver, CancellationCheck], Awaitable[dict[str, Any]]
]
RecordLoader = Callable[[str, Session], list[Any]]


@dataclass(frozen=True)
class ProjectJobOperations:
    plan: PlanOperation
    sample: SampleOperation
    generate: GenerateOperation
    load_slides: RecordLoader
    load_sources: RecordLoader


class ProjectJobService:
    """Owns durable project-job orchestration outside the HTTP route module."""

    def __init__(
        self,
        operations: ProjectJobOperations,
        *,
        manager: JobManager = job_manager,
        workflow: BoundedWorkflowRunner | None = None,
    ) -> None:
        self.operations = operations
        self.manager = manager
        self.workflow = workflow or BoundedWorkflowRunner()

    async def _set_page_event(self, job_id: str, event: dict[str, Any]) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            checkpoint = dict(job.checkpoint or {})
            counts = event.get("counts") or {}
            total = max(1, int(event.get("total") or 1))
            finished = sum(
                int(counts.get(name) or 0) for name in ("ready", "failed", "cancelled")
            )
            progress = max(float(job.progress or 0), min(0.88, 0.18 + 0.68 * finished / total))
            status = event.get("status")
            position = event.get("position")
            if status == "ready":
                label = f"第 {position} 页已完成（{finished}/{total}）"
            elif status == "failed":
                label = f"第 {position} 页生成失败，其他页面继续"
            elif status == "cancelled":
                label = f"第 {position} 页未启动，已响应取消请求"
            elif status == "running":
                label = f"正在渲染第 {position} 页"
            else:
                label = "页面任务已进入等待队列"
            checkpoint.update(
                {
                    "stage": "rendering_pages",
                    "label": label,
                    "pages": event.get("pages") or [],
                    "pageCounts": counts,
                }
            )
            job.status = "running"
            job.progress = progress
            job.checkpoint = checkpoint
            db.commit()
            snapshot = job_view(job)
        await self.manager.publish(job_id, {**snapshot, "type": "page_progress"})

    async def _set_node_event(self, job_id: str, state: dict[str, Any]) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            checkpoint = dict(job.checkpoint or {})
            nodes = dict(checkpoint.get("nodes") or {})
            nodes[state["name"]] = state
            node_status = state.get("status")
            label = {
                "running": f"正在执行工作流节点：{state['name']}",
                "retrying": f"节点 {state['name']} 暂时失败，正在安全重试",
                "completed": f"工作流节点 {state['name']} 已完成",
                "failed": f"工作流节点 {state['name']} 执行失败",
            }.get(node_status, f"工作流节点 {state['name']} 状态已更新")
            progress = float(job.progress or 0)
            if node_status == "completed":
                progress = max(
                    progress,
                    {
                        "source_ready": 0.18,
                        "evidence_gate": 0.18,
                        "plan": 0.9,
                        "render_sample": 0.9,
                        "render_candidates": 0.9,
                        "full_generation": 0.9,
                        "visual_gate": 0.91,
                        "targeted_repair": 0.915,
                        "assemble": 0.92,
                        "delivery_gate": 0.93,
                    }.get(state["name"], progress),
                )
            checkpoint.update(
                {"stage": f"node:{state['name']}", "label": label, "nodes": nodes}
            )
            job.checkpoint = checkpoint
            job.progress = progress
            db.commit()
            snapshot = job_view(job)
        await self.manager.publish(job_id, {**snapshot, "type": "progress"})

    async def _run_node(self, job_id: str, contract, input_value):
        snapshot = self.manager.store.get(job_id)
        return await self.workflow.run_node(
            contract,
            input_value,
            checkpoint=snapshot["checkpoint"] if snapshot else {},
            on_update=lambda state: self._set_node_event(job_id, state),
        )

    async def run(
        self, job_id: str, project_id: str, kind: str, payload: dict[str, Any] | None = None
    ) -> None:
        start_label, work_label = JOB_LABELS[kind]
        from app.db.models import PersonalBinding
        from app.personalization.runtime import assert_current, generation_snapshot
        with SessionLocal() as context_db:
            binding = context_db.get(PersonalBinding, project_id)
            persisted_job = context_db.get(Job, job_id)
            if not persisted_job or persisted_job.status == "cancelled":
                return
            expected_epoch = (persisted_job.checkpoint or {}).get("workflow", {}).get("personalizationEpoch")
            snapshot = binding.snapshot if binding else None
            if expected_epoch and (not snapshot or snapshot.get("epoch") != expected_epoch):
                await self._cancel(job_id, project_id, JobCancelled("个人经验上下文已失效"))
                return
        from app.security.accounts import owner_context
        from app.db.models import ProjectOwner
        with SessionLocal() as owner_db:
            project_owner = owner_db.get(ProjectOwner, project_id)
        owner_token = owner_context.set(project_owner.owner_id if project_owner else owner_context.get())
        context_token = generation_snapshot.set(snapshot)
        try:
            assert_current()
            await set_job_stage(job_id, 0.08, "preparing", start_label, self.manager)
            with SessionLocal() as db:
                project = db.get(Project, project_id)
                if not project:
                    raise HTTPException(404, "Project not found")
                artifact_root = project.artifact_path
                project.status = {
                    "outline": "planning",
                    "sample": "sampling",
                    "generate": "generating",
                    "full": "generating",
                }[kind]
                db.commit()
            await set_job_stage(job_id, 0.18, "working", work_label, self.manager)

            node_input = ProjectActionInput(
                job_id=job_id,
                project_id=project_id,
                kind=kind,
                payload=payload or {},
                artifact_root=artifact_root,
            )
            gate_input = ProjectGateInput(**node_input.model_dump(), summary={})

            async def check_source_ready(input_value: ProjectGateInput) -> ProjectGateOutput:
                with SessionLocal() as db:
                    project = db.get(Project, input_value.project_id)
                    if not project:
                        raise HTTPException(404, "Project not found")
                    slides = self.operations.load_slides(input_value.project_id, db)
                if input_value.kind not in {"outline", "full"} and not slides:
                    raise HTTPException(409, "请先生成大纲")
                return ProjectGateOutput(
                    passed=True, status="ready", details={"slideCount": len(slides)}
                )

            await self._run_node(
                job_id,
                NodeContract(
                    name="source_ready",
                    input_model=ProjectGateInput,
                    output_model=ProjectGateOutput,
                    handler=check_source_ready,
                ),
                gate_input,
            )

            async def check_evidence_gate(input_value: ProjectGateInput) -> ProjectGateOutput:
                with SessionLocal() as db:
                    sources = self.operations.load_sources(input_value.project_id, db)
                    slides = self.operations.load_slides(input_value.project_id, db)
                content_slides = [
                    slide
                    for slide in slides
                    if slide.get("role") not in {"cover", "agenda", "questions"}
                ]
                bound = sum(bool(slide.get("sourceRefs")) for slide in content_slides)
                return ProjectGateOutput(
                    passed=True,
                    status="source-bound" if sources else "brief-only",
                    details={
                        "sourceCount": len(sources),
                        "contentSlides": len(content_slides),
                        "preboundSlides": bound,
                    },
                )

            if kind == "generate":
                await self._run_node(
                    job_id,
                    NodeContract(
                        name="evidence_gate",
                        input_model=ProjectGateInput,
                        output_model=ProjectGateOutput,
                        handler=check_evidence_gate,
                    ),
                    gate_input,
                )

            async def execute_action(input_value: ProjectActionInput) -> ProjectActionOutput:
                with SessionLocal() as db:
                    if input_value.kind == "outline":
                        summary = await self.operations.plan(
                            input_value.project_id, input_value.payload, db
                        )
                        success_status = "outline_ready"
                    elif input_value.kind == "sample":
                        summary = await self.operations.sample(input_value.project_id, db)
                        success_status = "sample_ready"
                    elif input_value.kind == "full":
                        automatic_payload = dict(input_value.payload)
                        automatic_payload["approval_mode"] = False
                        automatic_slide_count = max(
                            1, int(automatic_payload.get("slide_count") or 20)
                        )
                        plan_task = asyncio.create_task(
                            self.operations.plan(input_value.project_id, automatic_payload, db)
                        )
                        waited_seconds = 0
                        while not plan_task.done():
                            try:
                                plan_summary = await asyncio.wait_for(
                                    asyncio.shield(plan_task), timeout=12
                                )
                                break
                            except TimeoutError:
                                waited_seconds += 12
                                await set_job_stage(
                                    job_id,
                                    min(0.42, 0.18 + waited_seconds / 600),
                                    "planning",
                                    f"正在分批规划 {automatic_slide_count} 页内容，已等待 {waited_seconds} 秒",
                                    self.manager,
                                )
                        else:
                            plan_summary = await plan_task
                        generation_summary = await self.operations.generate(
                            input_value.project_id,
                            db,
                            lambda event: self._set_page_event(job_id, event),
                            lambda: self.manager.cancellation_requested(job_id),
                        )
                        summary = {
                            **generation_summary,
                            "plannedSlides": plan_summary.get("slides", 0),
                            "automation": "full",
                        }
                        success_status = "partial" if summary.get("failedPages") else "ready"
                    else:
                        summary = await self.operations.generate(
                            input_value.project_id,
                            db,
                            lambda event: self._set_page_event(job_id, event),
                            lambda: self.manager.cancellation_requested(job_id),
                        )
                        success_status = "partial" if summary.get("failedPages") else "ready"
                expected = expected_project_artifacts(input_value, None)
                return ProjectActionOutput(
                    summary=summary,
                    success_status=success_status,
                    artifacts=[path for path in expected if Path(path).exists()],
                )

            action_result = await self._run_node(
                job_id,
                NodeContract(
                    name=project_node_name(node_input.kind),
                    input_model=ProjectActionInput,
                    output_model=ProjectActionOutput,
                    handler=execute_action,
                    max_attempts=2 if node_input.kind == "sample" else 1,
                    retry_for=(EngineError,) if node_input.kind == "sample" else (),
                    artifact_paths=expected_project_artifacts,
                ),
                node_input,
            )
            summary = action_result.output.summary
            success_status = action_result.output.success_status
            completed_input = ProjectGateInput(**node_input.model_dump(), summary=summary)
            await self._run_post_action_gates(job_id, node_input, completed_input)

            await set_job_stage(
                job_id,
                0.94,
                "finalizing",
                "正在保存结果并更新项目状态",
                self.manager,
            )
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                project = db.get(Project, project_id)
                assert_current()
                if not job or job.status == "cancelled":
                    return
                checkpoint = append_stage_trace(
                    job.checkpoint or {}, "completed", "任务已完成", 1.0
                )
                checkpoint["result"] = summary
                job.status = "completed"
                job.progress = 1.0
                job.checkpoint = checkpoint
                job.error = None
                if project:
                    project.status = success_status
                db.commit()
                snapshot = job_view(job)
            await self.manager.publish(job_id, {**snapshot, "type": "completed"})
        except JobCancelled as exc:
            await self._cancel(job_id, project_id, exc)
        except Exception as exc:  # noqa: BLE001 - job boundary persists every failure
            await self._fail(job_id, project_id, exc)
        finally:
            generation_snapshot.reset(context_token)
            owner_context.reset(owner_token)

    async def _run_post_action_gates(
        self,
        job_id: str,
        node_input: ProjectActionInput,
        input_value: ProjectGateInput,
    ) -> None:
        async def visual_gate(value: ProjectGateInput) -> ProjectGateOutput:
            reflection = value.summary.get("visualReflection") or {}
            return ProjectGateOutput(
                passed=True,
                status=str(reflection.get("visionStatus") or "not-applicable"),
                details={
                    "checked": reflection.get("checked", 0),
                    "applied": reflection.get("applied", 0),
                },
            )

        async def targeted_repair(value: ProjectGateInput) -> ProjectGateOutput:
            reflection = value.summary.get("visualReflection") or {}
            applied = int(reflection.get("applied") or 0)
            return ProjectGateOutput(
                passed=True,
                status="applied" if applied else "not-needed",
                details={"applied": applied},
            )

        async def assembly(value: ProjectGateInput) -> ProjectGateOutput:
            if value.summary.get("failedPages"):
                return ProjectGateOutput(
                    passed=True,
                    status="skipped-partial",
                    details={"readySlides": value.summary.get("readySlides", 0)},
                )
            expected = expected_project_artifacts(node_input, None)
            missing = [path for path in expected if not Path(path).is_file()]
            if missing:
                raise RuntimeError(f"组装产物缺失：{', '.join(missing)}")
            return ProjectGateOutput(passed=True, status="assembled", artifacts=expected)

        async def delivery(value: ProjectGateInput) -> ProjectGateOutput:
            expected = expected_project_artifacts(node_input, None)
            existing = [path for path in expected if Path(path).is_file()]
            if value.summary.get("failedPages"):
                if int(value.summary.get("readySlides") or 0) < 1:
                    raise RuntimeError("没有可交付的成功页面")
                return ProjectGateOutput(
                    passed=True,
                    status="partial-ready",
                    details={"readySlides": value.summary.get("readySlides", 0)},
                    artifacts=existing,
                )
            if len(existing) != len(expected):
                missing = sorted(set(expected) - set(existing))
                raise RuntimeError(f"交付门禁发现产物缺失：{', '.join(missing)}")
            return ProjectGateOutput(passed=True, status="ready", artifacts=existing)

        if node_input.kind in {"generate", "full"}:
            for name, handler, artifacts in (
                ("visual_gate", visual_gate, gate_artifacts),
                ("targeted_repair", targeted_repair, None),
                ("assemble", assembly, gate_artifacts),
            ):
                await self._run_node(
                    job_id,
                    NodeContract(
                        name=name,
                        input_model=ProjectGateInput,
                        output_model=ProjectGateOutput,
                        handler=handler,
                        artifact_paths=artifacts,
                    ),
                    input_value,
                )
        await self._run_node(
            job_id,
            NodeContract(
                name="delivery_gate",
                input_model=ProjectGateInput,
                output_model=ProjectGateOutput,
                handler=delivery,
                artifact_paths=gate_artifacts,
            ),
            input_value,
        )

    async def _cancel(self, job_id: str, project_id: str, exc: Exception) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            project = db.get(Project, project_id)
            if not job:
                return
            checkpoint = append_stage_trace(
                job.checkpoint or {}, "cancelled", str(exc), job.progress
            )
            job.status = "cancelled"
            job.error = None
            job.checkpoint = checkpoint
            if project:
                workflow = checkpoint.get("workflow") or {}
                project.status = workflow.get("previousProjectStatus") or "ready"
            db.commit()
            snapshot = job_view(job)
        await self.manager.publish(job_id, {**snapshot, "type": "cancelled"})

    async def _fail(self, job_id: str, project_id: str, exc: Exception) -> None:
        message = friendly_job_error(exc)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job and job.status == "cancelled":
                return
            project = db.get(Project, project_id)
            if job:
                checkpoint = append_stage_trace(
                    job.checkpoint or {}, "failed", message, job.progress
                )
                job.status = "failed"
                job.error = message
                job.checkpoint = checkpoint
            if project:
                project.status = "error"
            db.commit()
            snapshot = (
                job_view(job)
                if job
                else {"status": "failed", "progress": 0, "checkpoint": {}, "error": message}
            )
        await self.manager.publish(job_id, {**snapshot, "type": "failed"})

    def resume(self, snapshot: dict[str, Any]):
        workflow = (snapshot.get("checkpoint") or {}).get("workflow") or {}
        return self.run(
            snapshot["id"],
            snapshot["project_id"],
            snapshot["kind"],
            workflow.get("payload") or {},
        )
