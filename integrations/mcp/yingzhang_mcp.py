#!/usr/bin/env python3
"""映章 YingZhang MCP server (stdio, JSON-RPC 2.0, no MCP SDK).

Wraps a running YingZhang REST API so MCP clients (Claude Desktop, Claude Code,
Codex, Cursor, ...) can create projects, upload materials, confirm the outline and
representative sample, generate, review quality and export decks.

Transport: newline-delimited JSON-RPC 2.0 messages on stdin/stdout (MCP stdio).
Logs go to stderr only. Only dependency: ``httpx`` (already required by YingZhang).

Environment:
  YINGZHANG_API_URL          REST base URL (default http://127.0.0.1:8000)
  YINGZHANG_MCP_EXPORT_DIR   where exported files are written (default ./yingzhang-exports)
  YINGZHANG_MCP_POLL_SECONDS job polling interval (default 2)
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

SERVER_INFO = {"name": "yingzhang", "title": "映章 YingZhang", "version": "0.2.0"}
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
GATE_MESSAGE = "请先确认大纲与代表样张，再批量生成"
DEFAULT_WAIT_SECONDS = 45
PLAN_FIELDS = (
    "title", "instructions", "preset", "slide_count", "audience", "objective",
    "tone", "duration_minutes", "brand_name", "image_mode", "skill_ids",
)
PRESETS = [
    "academic", "conference", "business", "strategy", "executive", "review", "product",
    "pitch", "marketing", "sales", "teaching", "training", "public", "keynote", "portfolio",
]
INSTRUCTIONS = (
    "映章（YingZhang）本地 AI 演示生产系统。推荐流程：create_project → upload_sources → "
    "plan_outline（默认开启确认门禁）→ 向用户展示大纲并获得确认 → generate_deck(confirm_outline=true) "
    "→ 展示代表样张并获得确认 → generate_deck(confirm_sample=true) → evaluate → export。"
    "长任务返回 job_id 时用 get_job_status 轮询。不要替用户确认大纲或样张。"
)

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = (
    -32700, -32600, -32601, -32602, -32603,
)


def log(message: str) -> None:
    print(f"[yingzhang-mcp] {message}", file=sys.stderr, flush=True)


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail_text(detail)}")


class ToolError(Exception):
    """A tool-level failure reported to the model as ``isError: true``."""


class InvalidParams(Exception):
    pass


def detail_text(detail: Any) -> str:
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("detail") or json.dumps(detail, ensure_ascii=False))
    if isinstance(detail, list):
        return "; ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail)
    return str(detail)


class YingZhangApi:
    def __init__(self, base_url: str, client: httpx.Client | None = None, timeout: float = 600):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(base_url=self.base_url, timeout=timeout, trust_env=False)

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.client.request(method, "/api/v1" + path, **kwargs)
        except httpx.HTTPError as exc:
            raise ToolError(
                f"无法连接映章服务 {self.base_url}（{exc.__class__.__name__}）。请先启动服务："
                "uv run --locked python -m uvicorn app.main:app --app-dir apps/api --port 8000，"
                "或设置 YINGZHANG_API_URL。"
            ) from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text[:500]
            raise ApiError(response.status_code, detail)
        return response

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(method, path, **kwargs)
        return response.json() if response.content else None


def _filename(response: httpx.Response, fallback: str) -> str:
    header = response.headers.get("content-disposition", "")
    match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", header) or re.search(r'filename="?([^";]+)"?', header)
    name = unquote(match.group(1).strip()) if match else fallback
    return Path(name).name or fallback


def _slug(value: str) -> str:
    return re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-")[:60] or "presentation"


def _job_summary(job: dict) -> dict:
    checkpoint = job.get("checkpoint") or {}
    summary = {
        "job_id": job.get("id"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "progress": round(float(job.get("progress") or 0), 3),
        "stage": checkpoint.get("stage"),
        "label": checkpoint.get("label"),
        "error": job.get("error"),
    }
    if checkpoint.get("pageCounts"):
        summary["page_counts"] = checkpoint["pageCounts"]
    if checkpoint.get("result") is not None:
        summary["result"] = checkpoint["result"]
    if job.get("status") not in TERMINAL_STATUSES:
        summary["next"] = "任务仍在运行，请稍后调用 get_job_status 继续查询。"
    return summary


def _slide_summary(slide: dict) -> dict:
    content = slide.get("content") or {}
    return {
        "slide_id": slide.get("id"),
        "position": slide.get("position"),
        "role": slide.get("role"),
        "revision": slide.get("revision"),
        "title": content.get("title"),
        "message": slide.get("message"),
        "bullets": list(content.get("bullets") or [])[:8],
    }


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


PROJECT_ID = {"type": "string", "description": "项目 ID（create_project 或 list_projects 返回）"}
WAIT = {"type": "integer", "minimum": 0, "maximum": 600, "description": "最多等待任务完成的秒数；超时返回 job_id 供 get_job_status 轮询"}
BRIEF_PROPERTIES = {
    "title": {"type": "string", "description": "演示主题/标题"},
    "preset": {"type": "string", "enum": PRESETS, "description": "演示类型，默认 academic"},
    "instructions": {"type": "string", "description": "创作要求（重点、结构、限制）"},
    "audience": {"type": "string", "description": "目标受众"},
    "objective": {"type": "string", "description": "沟通目标"},
    "slide_count": {"type": "integer", "minimum": 6, "maximum": 60, "description": "目标页数"},
    "tone": {"type": "string", "enum": ["auto", "formal", "executive", "editorial", "energetic"]},
    "duration_minutes": {"type": "integer", "minimum": 3, "maximum": 180},
}


class YingZhangTools:
    def __init__(self, api: YingZhangApi, export_dir: Path, poll_seconds: float = 2.0):
        self.api = api
        self.export_dir = export_dir
        self.poll_seconds = poll_seconds
        self.briefs: dict[str, dict] = {}

    # -- tool catalogue -------------------------------------------------
    def definitions(self) -> list[dict]:
        read_only = {"readOnlyHint": True, "openWorldHint": False}
        return [
            {"name": "list_projects", "title": "列出项目", "description": "列出映章中的演示项目（ID、名称、状态）。",
             "inputSchema": _schema({}), "annotations": read_only},
            {"name": "create_project", "title": "新建项目",
             "description": "新建演示项目并记录创作简报；简报会作为本会话中 plan_outline 的默认值。",
             "inputSchema": _schema(BRIEF_PROPERTIES, ["title"])},
            {"name": "upload_sources", "title": "上传材料",
             "description": "把本机文件（PDF、DOCX、XLSX、CSV、PPTX、Markdown、HTML、图片）上传为项目材料并返回读取情况。",
             "inputSchema": _schema({"project_id": PROJECT_ID, "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "本机文件绝对路径"}}, ["project_id", "paths"])},
            {"name": "plan_outline", "title": "规划大纲",
             "description": "后台规划叙事与逐页大纲并返回大纲摘要。默认开启确认门禁：生成后必须先由用户确认大纲与代表样张。",
             "inputSchema": _schema({"project_id": PROJECT_ID, **BRIEF_PROPERTIES,
                                     "approval_mode": {"type": "boolean", "description": "是否启用大纲/样张确认门禁，默认 true"},
                                     "wait_seconds": WAIT}, ["project_id"])},
            {"name": "generate_deck", "title": "生成演示",
             "description": (
                 "按门禁推进生成：大纲未确认时返回待确认大纲；confirm_outline=true 后生成代表样张并等待确认；"
                 "confirm_sample=true 后批量生成全部页面。automatic=true 时跳过门禁一次性规划并生成。"
                 f"服务端规则：{GATE_MESSAGE}。"
             ),
             "inputSchema": _schema({"project_id": PROJECT_ID,
                                     "confirm_outline": {"type": "boolean", "description": "用户已确认大纲"},
                                     "confirm_sample": {"type": "boolean", "description": "用户已检查并确认代表样张"},
                                     "automatic": {"type": "boolean", "description": "跳过门禁，按简报自动规划并生成全稿"},
                                     **{key: value for key, value in BRIEF_PROPERTIES.items()},
                                     "wait_seconds": WAIT}, ["project_id"])},
            {"name": "get_job_status", "title": "查询任务", "description": "查询后台任务进度；wait_seconds>0 时等待直到完成或超时。",
             "inputSchema": _schema({"job_id": {"type": "string"}, "wait_seconds": WAIT}, ["job_id"]), "annotations": read_only},
            {"name": "list_slides", "title": "页面列表", "description": "列出项目页面（ID、序号、修订号、标题、结论、要点）及门禁状态。",
             "inputSchema": _schema({"project_id": PROJECT_ID}, ["project_id"]), "annotations": read_only},
            {"name": "edit_slide", "title": "修改页面对象",
             "description": (
                 "用自然语言指令修改单页对象，例如“把标题改为…”“改写第二个要点”“修改核心结论”。"
                 "instruction 用于识别对象，value 为新内容；可显式给出 target={kind:title|message|bullet|bullets|visual,index}。"
             ),
             "inputSchema": _schema({"project_id": PROJECT_ID,
                                     "slide_id": {"type": "string"}, "position": {"type": "integer", "minimum": 1},
                                     "instruction": {"type": "string", "minLength": 2},
                                     "value": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                                     "operation": {"type": "string", "enum": ["replace", "append", "delete", "move"]},
                                     "target": {"type": "object"},
                                     "rerender": {"type": "boolean", "description": "修改后重新渲染该页，默认 true"}},
                                    ["project_id", "instruction"])},
            {"name": "evaluate", "title": "质量检查",
             "description": "运行内容完整性、证据覆盖与视觉质量检查，并在可用时创建专业评估记录。",
             "inputSchema": _schema({"project_id": PROJECT_ID}, ["project_id"])},
            {"name": "export", "title": "导出",
             "description": "导出 pptx / pdf / html，或 video（讲解视频 MP4 + SRT），保存到本机并返回文件路径。",
             "inputSchema": _schema({"project_id": PROJECT_ID,
                                     "format": {"type": "string", "enum": ["pptx", "pdf", "html", "video"]},
                                     "stage": {"type": "string", "enum": ["draft", "final"], "description": "final 需通过质量检查"},
                                     "output_dir": {"type": "string", "description": "保存目录，默认 YINGZHANG_MCP_EXPORT_DIR"},
                                     "tts": {"type": "boolean", "description": "video：使用已配置的 tts 模型配音，默认 true"},
                                     "wait_seconds": WAIT}, ["project_id", "format"])},
        ]

    def call(self, name: str, arguments: dict) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None or name not in {tool["name"] for tool in self.definitions()}:
            raise InvalidParams(f"Unknown tool: {name}")
        schema = next(tool["inputSchema"] for tool in self.definitions() if tool["name"] == name)
        missing = [key for key in schema["required"] if arguments.get(key) in (None, "", [])]
        if missing:
            raise InvalidParams(f"Missing required arguments: {', '.join(missing)}")
        unknown = sorted(set(arguments) - set(schema["properties"]))
        if unknown:
            raise InvalidParams(f"Unknown arguments: {', '.join(unknown)}")
        try:
            return handler(**arguments)
        except ApiError as exc:
            raise ToolError(self._api_error_message(exc)) from exc

    @staticmethod
    def _api_error_message(exc: ApiError) -> str:
        text = detail_text(exc.detail)
        if exc.status == 409 and ("确认" in text or GATE_MESSAGE in text):
            return f"{text}。请先 plan_outline，并在用户确认后依次调用 generate_deck(confirm_outline=true) 与 generate_deck(confirm_sample=true)。"
        return f"映章服务返回 HTTP {exc.status}：{text}"

    # -- helpers ---------------------------------------------------------
    def _wait(self, job: dict, wait_seconds: int | None) -> dict:
        deadline = time.monotonic() + (DEFAULT_WAIT_SECONDS if wait_seconds is None else wait_seconds)
        while job.get("status") not in TERMINAL_STATUSES and time.monotonic() < deadline:
            time.sleep(min(self.poll_seconds, max(0.0, deadline - time.monotonic())))
            job = self.api.json("GET", f"/jobs/{job['id']}")
        return job

    def _workspace(self, project_id: str) -> dict:
        return self.api.json("GET", f"/projects/{project_id}/workspace")

    def _plan_body(self, project_id: str, arguments: dict, approval_mode: bool) -> dict:
        body = {**self.briefs.get(project_id, {})}
        body.update({key: value for key, value in arguments.items() if key in PLAN_FIELDS and value is not None})
        if not body.get("title"):
            project = next((item for item in self.api.json("GET", "/projects") if item["id"] == project_id), None)
            if not project:
                raise ToolError(f"项目 {project_id} 不存在")
            body["title"] = project["name"]
        body["approval_mode"] = approval_mode
        return body

    def _outline(self, project_id: str) -> dict:
        workspace = self._workspace(project_id)
        return {
            "project_id": project_id,
            "gates": workspace.get("gates"),
            "sample_available": workspace.get("sampleAvailable"),
            "preview_available": workspace.get("previewAvailable"),
            "slides": [_slide_summary(slide) for slide in workspace.get("slides") or []],
        }

    # -- tools ------------------------------------------------------------
    def tool_list_projects(self) -> dict:
        projects = self.api.json("GET", "/projects")
        return {"projects": [{"project_id": p["id"], "name": p["name"], "status": p["status"]} for p in projects]}

    def tool_create_project(self, title: str, **brief: Any) -> dict:
        project = self.api.json("POST", "/projects", json={"name": title})
        self.briefs[project["id"]] = {"title": title, **{k: v for k, v in brief.items() if v is not None}}
        return {
            "project_id": project["id"], "name": project["name"], "status": project["status"],
            "brief": self.briefs[project["id"]],
            "next": "调用 upload_sources 上传材料（可选），再调用 plan_outline 生成大纲。",
        }

    def tool_upload_sources(self, project_id: str, paths: list[str]) -> dict:
        uploaded, failed = [], []
        for raw in paths:
            path = Path(raw).expanduser()
            if not path.is_file():
                failed.append({"path": raw, "error": "文件不存在或不是普通文件"})
                continue
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            try:
                with path.open("rb") as stream:
                    view = self.api.json(
                        "POST", f"/projects/{project_id}/sources",
                        files={"file": (path.name, stream, media_type)},
                    )
            except ApiError as exc:
                failed.append({"path": raw, "error": self._api_error_message(exc)})
                continue
            uploaded.append({
                "source_id": view.get("id"), "name": view.get("name"),
                "sections": view.get("sections"), "reading_status": view.get("readingStatus"),
                "warnings": [item.get("message") for item in view.get("readingWarnings") or []][:10],
            })
        if not uploaded:
            raise ToolError("没有成功上传的材料：" + json.dumps(failed, ensure_ascii=False))
        return {"uploaded": uploaded, "failed": failed}

    def tool_plan_outline(self, project_id: str, approval_mode: bool = True, wait_seconds: int | None = None, **brief: Any) -> dict:
        body = self._plan_body(project_id, brief, approval_mode)
        job = self._wait(self.api.json("POST", f"/projects/{project_id}/jobs/outline", json=body), wait_seconds)
        result = {"job": _job_summary(job)}
        if job.get("status") == "completed":
            result["outline"] = self._outline(project_id)
            result["next"] = (
                "请把大纲展示给用户并等待确认；确认后调用 generate_deck(confirm_outline=true)。"
                if approval_mode else "可调用 generate_deck 生成全部页面。"
            )
        elif job.get("status") == "failed":
            raise ToolError(f"大纲规划失败：{job.get('error')}")
        return result

    def tool_generate_deck(
        self, project_id: str, confirm_outline: bool = False, confirm_sample: bool = False,
        automatic: bool = False, wait_seconds: int | None = None, **brief: Any,
    ) -> dict:
        if automatic:
            body = self._plan_body(project_id, brief, approval_mode=False)
            job = self._wait(self.api.json("POST", f"/projects/{project_id}/jobs/full", json=body), wait_seconds)
            return {"job": _job_summary(job)}
        workspace = self._workspace(project_id)
        if not workspace.get("slides"):
            raise ToolError("项目还没有大纲，请先调用 plan_outline。")
        gates = workspace.get("gates") or {}
        if gates.get("enabled"):
            if gates.get("outline") != "approved":
                if not confirm_outline:
                    return {
                        "status": "awaiting_outline_confirmation",
                        "message": f"{GATE_MESSAGE}。请向用户展示大纲，获得确认后以 confirm_outline=true 重新调用。",
                        "outline": self._outline(project_id),
                    }
                self.api.json("POST", f"/projects/{project_id}/gates/outline/approve")
            if gates.get("sample") != "approved":
                if not workspace.get("sampleAvailable") or not confirm_sample:
                    pending: dict[str, Any] = {
                        "status": "awaiting_sample_confirmation",
                        "message": f"{GATE_MESSAGE}。请让用户检查代表样张，确认后以 confirm_sample=true 重新调用。",
                        "sample_preview_url": f"{self.api.base_url}/api/v1/projects/{project_id}/sample/html",
                    }
                    if not workspace.get("sampleAvailable"):
                        job = self.api.json("POST", f"/projects/{project_id}/jobs/sample")
                        job = self._wait(job, wait_seconds)
                        if job.get("status") == "failed":
                            raise ToolError(f"代表样张生成失败：{job.get('error')}")
                        pending["job"] = _job_summary(job)
                    return pending
                self.api.json("POST", f"/projects/{project_id}/gates/sample/approve")
        job = self._wait(self.api.json("POST", f"/projects/{project_id}/jobs/generate"), wait_seconds)
        return {"status": "generating" if job.get("status") not in TERMINAL_STATUSES else job.get("status"),
                "job": _job_summary(job)}

    def tool_get_job_status(self, job_id: str, wait_seconds: int | None = 0) -> dict:
        job = self._wait(self.api.json("GET", f"/jobs/{job_id}"), wait_seconds or 0)
        return _job_summary(job)

    def tool_list_slides(self, project_id: str) -> dict:
        return self._outline(project_id)

    def tool_edit_slide(
        self, project_id: str, instruction: str, slide_id: str | None = None, position: int | None = None,
        value: str | list[str] | None = None, operation: str = "replace", target: dict | None = None,
        rerender: bool = True,
    ) -> dict:
        slides = self._workspace(project_id).get("slides") or []
        slide = next((item for item in slides if (slide_id and item.get("id") == slide_id)
                      or (position and item.get("position") == position)), None)
        if not slide:
            raise ToolError("未找到指定页面；请先用 list_slides 获取 slide_id 或 position。")
        if value is None and operation in {"replace", "append"}:
            raise ToolError("replace/append 修改需要提供 value（新的文字内容）。")
        body = {"instruction": instruction, "operation": operation, "value": value,
                "target": target or {}, "rerender": rerender, "revision": slide.get("revision")}
        result = self.api.json("POST", f"/projects/{project_id}/slides/{slide['id']}/chat", json=body)
        return {
            "slide": _slide_summary({**result["slide"], "revision": result.get("version")}),
            "change": {key: (result.get("changeSet") or {}).get(key) for key in ("target", "operation", "before", "after")},
            "rerendered": bool(result.get("render")),
        }

    def tool_evaluate(self, project_id: str) -> dict:
        try:
            report = self.api.json("POST", f"/projects/{project_id}/validate")
        except ApiError as exc:
            if exc.status in {404, 405}:
                return {"available": False, "message": "当前映章版本未提供质量检查接口"}
            raise
        issues = report.get("issues") or []
        result = {
            "available": True,
            "passed": report.get("passed"),
            "blocking_errors": report.get("blockingErrors"),
            "warning_count": report.get("warningCount"),
            "claim_coverage": report.get("claimCoverage"),
            "issues": issues[:20],
            "issues_truncated": max(0, len(issues) - 20),
        }
        try:
            evaluation = self.api.json("POST", f"/projects/{project_id}/evaluations")
            result["evaluation"] = {"id": evaluation.get("id"), "suite": evaluation.get("suite")}
        except ApiError as exc:
            if exc.status not in {404, 405, 409, 422}:
                raise
            result["evaluation"] = None
        return result

    def tool_export(
        self, project_id: str, format: str, stage: str = "draft", output_dir: str | None = None,
        tts: bool = True, wait_seconds: int | None = None,
    ) -> dict:
        folder = Path(output_dir).expanduser() if output_dir else self.export_dir
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        if format == "video":
            job = self.api.json("POST", f"/projects/{project_id}/jobs/video", json={"tts": tts})
            job = self._wait(job, 300 if wait_seconds is None else wait_seconds)
            if job.get("status") != "completed":
                if job.get("status") in TERMINAL_STATUSES:
                    raise ToolError(f"讲解视频导出失败：{job.get('error')}")
                return {"status": "rendering", "job": _job_summary(job)}
            files = {}
            for suffix, params in ((".mp4", {}), (".srt", {"subtitles": "true"})):
                try:
                    response = self.api.request("GET", f"/projects/{project_id}/export/video", params=params)
                except ApiError:
                    if suffix == ".srt":
                        continue
                    raise
                files[suffix] = self._save(folder, f"{_slug(project_id[:8])}-{stamp}{suffix}", response.content)
            return {"format": "video", "path": files[".mp4"]["path"], "files": list(files.values()),
                    "job": _job_summary(job)}
        if format not in {"pptx", "pdf", "html"}:
            raise ToolError("format 仅支持 pptx、pdf、html、video")
        response = self.api.request("POST", f"/projects/{project_id}/export/{format}", params={"stage": stage})
        server_name = _filename(response, f"presentation.{format}")
        suffix = "".join(Path(server_name).suffixes[-1:]) or f".{format}"
        saved = self._save(folder, f"{_slug(Path(server_name).stem)}-{project_id[:8]}-{stamp}{suffix}", response.content)
        return {"format": format, "stage": stage, **saved}

    @staticmethod
    def _save(folder: Path, name: str, data: bytes) -> dict:
        target = (folder / name).resolve()
        target.write_bytes(data)
        return {"path": str(target), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class McpServer:
    def __init__(self, tools: YingZhangTools):
        self.tools = tools
        self.protocol_version = LATEST_PROTOCOL_VERSION
        self.initialized = False

    def handle(self, message: Any) -> dict | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            if isinstance(message, dict) and "method" not in message and ("result" in message or "error" in message):
                return None  # response to a server request we never send
            return self._error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Invalid Request")
        method, params, request_id = message["method"], message.get("params") or {}, message.get("id")
        is_notification = "id" not in message
        if is_notification:
            if method == "notifications/initialized":
                self.initialized = True
            return None
        try:
            if method == "initialize":
                return self._result(request_id, self._initialize(params))
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": self.tools.definitions()})
            if method == "tools/call":
                return self._result(request_id, self._call_tool(params))
            return self._error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        except InvalidParams as exc:
            return self._error(request_id, INVALID_PARAMS, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the stdio loop
            log(f"internal error in {method}: {exc!r}")
            return self._error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")

    def _initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion")
        self.protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        info = dict(SERVER_INFO)
        if self.protocol_version < "2025-06-18":
            info.pop("title", None)
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": info,
            "instructions": INSTRUCTIONS,
        }

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise InvalidParams("tools/call requires a tool name and an arguments object")
        try:
            payload = self.tools.call(name, arguments)
            is_error = False
        except ToolError as exc:
            payload, is_error = {"error": str(exc)}, True
        text = payload["error"] if is_error else json.dumps(payload, ensure_ascii=False, indent=2)
        result: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": is_error}
        if not is_error and self.protocol_version >= "2025-06-18":
            result["structuredContent"] = payload
        return result

    @staticmethod
    def _result(request_id: Any, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                response = self._error(None, PARSE_ERROR, "Parse error")
            else:
                if isinstance(message, list):
                    # JSON-RPC batching is not part of MCP 2025-06-18.
                    response = self._error(None, INVALID_REQUEST, "Batch requests are not supported")
                else:
                    response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                stdout.flush()


def build_server() -> McpServer:
    base_url = os.environ.get("YINGZHANG_API_URL", "http://127.0.0.1:8000")
    export_dir = Path(os.environ.get("YINGZHANG_MCP_EXPORT_DIR", "yingzhang-exports")).expanduser()
    poll = float(os.environ.get("YINGZHANG_MCP_POLL_SECONDS", "2"))
    return McpServer(YingZhangTools(YingZhangApi(base_url), export_dir.resolve(), poll))


def main() -> None:
    # MCP stdio requires UTF-8 framing regardless of the console code page (Windows).
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", newline="\n" if stream is sys.stdout else None)
    server = build_server()
    log(f"serving {server.tools.api.base_url} over stdio")
    server.serve()


if __name__ == "__main__":
    main()
