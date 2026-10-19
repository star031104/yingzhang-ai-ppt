---
name: yingzhang-ppt
description: Drive the local 映章 YingZhang AI presentation system (FastAPI on http://127.0.0.1:8000) to turn source materials into an evidence-bound, editable PPTX/PDF/HTML deck or narrated MP4. Use when the user asks to make slides/PPT/演示/汇报/答辩 with YingZhang, upload materials, review or confirm an outline, generate, check quality, or export. Works through the yingzhang MCP tools when available, otherwise through the REST API.
---

# 映章 YingZhang：用 Agent 生成演示

映章把演示生产拆成：材料解析 → 大纲规划 → **人工确认大纲与代表样张** → 逐页生成 → 质量检查 → 导出。
你的职责是推进流程并把关键决定交给用户；**不得替用户确认大纲或样张**。

## 0. 确认服务可用

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health   # {"status":"ok",...}
```

未运行时，在仓库根目录启动（单进程，不要加 `--workers`）：

```bash
uv sync --locked && npm ci && npm run build
uv run --locked python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

或 `docker compose up -d`。模型服务需由用户在网页“模型配置”中填写；未配置时系统使用确定性规划，质量有限，应告知用户。

## 1. 工具选择

- 有 `yingzhang` MCP 工具（`create_project`、`plan_outline` …）时优先使用。
- 否则用 REST（前缀 `/api/v1`，下表）。长任务返回 job，需轮询 `GET /jobs/{id}` 直到 `completed|failed|cancelled`；可用 `scripts/poll_job.py <job_id>`。

| 步骤 | MCP 工具 | REST |
| --- | --- | --- |
| 新建项目 | `create_project(title, preset, instructions, audience, slide_count)` | `POST /projects {"name"}` |
| 上传材料 | `upload_sources(project_id, paths)` | `POST /projects/{id}/sources`（multipart `file`） |
| 规划大纲 | `plan_outline(project_id, …)` | `POST /projects/{id}/jobs/outline`（PlanRequest，`approval_mode:true`） |
| 查看大纲/页面 | `list_slides` | `GET /projects/{id}/workspace`（`slides`、`gates`） |
| 确认大纲 | `generate_deck(confirm_outline=true)` | `POST /projects/{id}/gates/outline/approve` |
| 代表样张 | 同上（自动生成） | `POST /projects/{id}/jobs/sample` → `GET /projects/{id}/sample/html` |
| 确认样张并全量生成 | `generate_deck(confirm_sample=true)` | `POST …/gates/sample/approve` → `POST …/jobs/generate` |
| 任务进度 | `get_job_status(job_id, wait_seconds)` | `GET /jobs/{job_id}` |
| 修改页面对象 | `edit_slide(position, instruction, value)` | `POST /projects/{id}/slides/{slide_id}/chat` |
| 质量检查 | `evaluate` | `POST /projects/{id}/validate` |
| 导出 | `export(format=pptx/pdf/html/video)` | `POST /projects/{id}/export/{pptx,pdf,html}?stage=draft` |
| 讲解视频 | `export(format="video")` | `POST /projects/{id}/jobs/video` → `GET /projects/{id}/export/video` |

## 2. 标准流程

1. **收集简报**：主题、受众、沟通目标、页数（6–60）、类型 `preset`（academic、business、executive、pitch、teaching 等）、语气与重点。缺关键信息时先问。
2. **上传材料**：使用本机绝对路径。检查返回的 `reading_status`/`warnings`（扫描件、截断、缺失数值），把风险告诉用户。
3. **规划大纲**：`plan_outline` 默认开启确认门禁。把每页 `position / title / message` 以简洁列表展示给用户，询问是否调整。
   - 调整页面文字用 `edit_slide`；结构性大改则带新的 `instructions` 重新 `plan_outline`。
4. **确认大纲**：仅在用户明确同意后调用 `generate_deck(confirm_outline=true)`，系统会渲染封面、中间页和结尾页三张代表样张，并返回 `sample_preview_url`。
5. **确认样张**：请用户在浏览器查看样张；用户同意后调用 `generate_deck(confirm_sample=true)` 开始全量生成。
   - 服务端会拒绝跳过门禁：`409 请先确认大纲与代表样张，再批量生成`。看到它时回到第 3–5 步，不要绕过。
   - 用户明确要求“一次性自动生成、不需要确认”时，才使用 `generate_deck(automatic=true)`。
6. **跟踪进度**：返回 `status: generating` 时，用 `get_job_status(job_id, wait_seconds=60)` 轮询，向用户报告页数进度；`failed` 时转述 `error`，部分失败页可在网页中单页重生成。
7. **质量复核**：`evaluate` 后汇报 `passed`、`blocking_errors` 与主要 `issues`（证据缺失、溢出、对比度、来源）。需要修改时用 `edit_slide`（会重新渲染该页），再复查。
8. **导出**：草稿用 `stage=draft`；正式交付 `stage=final` 需质量检查通过。返回值中的 `path` 是本机文件。提醒用户在目标 Office/WPS 中复核字体与排版。

## 3. 讲解视频（可选）

`export(format="video")` 生成 MP4 与 SRT：每页讲稿优先取演讲备注（`speakerIntent.narration`），否则取要点或由标题/结论确定性生成；已为 `tts` 角色配置语音模型时合成配音，否则生成按文字长度计时的静音片段。需要本机 `ffmpeg`（PATH 或 `YINGZHANG_FFMPEG`）。页面预览过期时会返回 409，先重新生成页面。

## 4. 注意事项

- 生成内容可能有事实错误；数字和结论以材料来源为准，提醒用户核验。
- 一个项目同一类型任务同时只运行一个；重复提交会返回正在运行的任务。队列满返回 503，稍后重试。
- 不要上传用户未授权的敏感材料；不要读取或输出 API Key。
- 修改页面时携带最新 `revision`（MCP 工具自动处理）；409 冲突表示页面已被修改，刷新后重试。
