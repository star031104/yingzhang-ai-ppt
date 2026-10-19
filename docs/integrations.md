# 映章：Agent 集成（MCP、Skill 与讲解视频）

映章的 REST API 是唯一事实来源。MCP 服务器与 Agent Skill 只是它的薄封装：门禁、权限、修订号和导出检查仍由服务端执行。

## MCP 服务器

`integrations/mcp/yingzhang_mcp.py` 是无 MCP SDK 依赖的 stdio 服务器（JSON-RPC 2.0，按行分隔），实现 `initialize`、`ping`、`tools/list`、`tools/call`，支持协议版本 `2025-06-18`（同时兼容 `2025-03-26`、`2024-11-05`，客户端请求未知版本时返回 `2025-06-18`）。唯一依赖 `httpx` 已包含在项目环境中。

先启动映章服务（见 README），再让客户端以子进程方式启动 MCP 服务器。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `YINGZHANG_API_URL` | `http://127.0.0.1:8000` | 映章服务地址 |
| `YINGZHANG_MCP_EXPORT_DIR` | `./yingzhang-exports` | `export` 工具写入文件的目录（相对 MCP 进程工作目录） |
| `YINGZHANG_MCP_POLL_SECONDS` | `2` | 等待后台任务时的轮询间隔 |

### 工具

| 工具 | 作用 | 对应接口 |
| --- | --- | --- |
| `list_projects` | 项目列表 | `GET /projects` |
| `create_project` | 新建项目并记录简报（title、preset、instructions、audience、slide_count…） | `POST /projects` |
| `upload_sources` | 上传本机文件并返回读取情况 | `POST /projects/{id}/sources` |
| `plan_outline` | 后台规划大纲（默认 `approval_mode=true`），返回逐页摘要与门禁状态 | `POST /projects/{id}/jobs/outline` |
| `generate_deck` | 按门禁推进：待确认大纲 → 生成代表样张待确认 → 全量生成；`automatic=true` 走 `jobs/full` | `gates/*/approve`、`jobs/sample`、`jobs/generate` |
| `get_job_status` | 查询或等待任务 | `GET /jobs/{id}` |
| `list_slides` | 页面、修订号与门禁 | `GET /projects/{id}/workspace` |
| `edit_slide` | 自然语言对象修改（标题、结论、第 N 个要点、要点列表、视觉类型） | `POST /projects/{id}/slides/{slide_id}/chat` |
| `evaluate` | 质量检查与专业评估（接口不存在时返回 `available:false`） | `POST /projects/{id}/validate`、`/evaluations` |
| `export` | 导出 pptx/pdf/html 或讲解视频，返回本机路径、大小与 SHA-256 | `/export/*`、`/jobs/video` |

服务端门禁文案 `请先确认大纲与代表样张，再批量生成` 会原样传给模型，并附带下一步提示。工具等待时间默认 45 秒（视频 300 秒），超时返回 `job_id`，由模型继续调用 `get_job_status`。

### 客户端配置

以下示例中 `/path/to/yingzhang-ai-ppt` 替换为仓库绝对路径；Windows 上 Python 路径为 `.venv\\Scripts\\python.exe`。

**Claude Desktop**（`claude_desktop_config.json`）与 **Cursor**（`~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`）：

```json
{
  "mcpServers": {
    "yingzhang": {
      "command": "/path/to/yingzhang-ai-ppt/.venv/bin/python",
      "args": ["/path/to/yingzhang-ai-ppt/integrations/mcp/yingzhang_mcp.py"],
      "env": {
        "YINGZHANG_API_URL": "http://127.0.0.1:8000",
        "YINGZHANG_MCP_EXPORT_DIR": "/path/to/exports"
      }
    }
  }
}
```

**Claude Code**：

```bash
claude mcp add yingzhang \
  -e YINGZHANG_API_URL=http://127.0.0.1:8000 \
  -- /path/to/yingzhang-ai-ppt/.venv/bin/python /path/to/yingzhang-ai-ppt/integrations/mcp/yingzhang_mcp.py
```

也可以在项目根目录的 `.mcp.json` 中写入与上面 Claude Desktop 相同的 `mcpServers` 结构。

**Codex**（`~/.codex/config.toml`）：

```toml
[mcp_servers.yingzhang]
command = "/path/to/yingzhang-ai-ppt/.venv/bin/python"
args = ["/path/to/yingzhang-ai-ppt/integrations/mcp/yingzhang_mcp.py"]
env = { YINGZHANG_API_URL = "http://127.0.0.1:8000" }
tool_timeout_sec = 300
```

未创建 `.venv` 时，可将命令换成 `uv`，参数为 `["run", "--project", "/path/to/yingzhang-ai-ppt", "python", "/path/to/yingzhang-ai-ppt/integrations/mcp/yingzhang_mcp.py"]`。服务运行在 Docker 中时只需把 `YINGZHANG_API_URL` 指向映射端口；MCP 服务器本身在宿主机运行，导出文件写到宿主机目录。

## Agent Skill

`integrations/skills/yingzhang-ppt/SKILL.md` 教 Claude Code / Codex 按“启动服务 → 上传材料 → 确认大纲 → 确认样张 → 生成 → 质量复核 → 导出”的顺序工作，并要求不替用户确认门禁。

- Claude Code：复制整个目录到 `~/.claude/skills/yingzhang-ppt/`（个人）或项目内 `.claude/skills/yingzhang-ppt/`。
- Codex：复制到 `~/.codex/skills/yingzhang-ppt/`，或在 `AGENTS.md` 中引用该文件。

没有 MCP 时，Skill 中的 REST 对照表和 `scripts/poll_job.py` 可直接配合 `curl` 使用。

## 讲解视频导出

“导出讲解视频”把每页讲稿、语音和渲染画面合成为 MP4，并生成 SRT 字幕（同时作为软字幕轨嵌入）。

1. **讲稿**：优先使用演讲备注 `speakerIntent.narration`（可先调用 `POST /projects/{id}/narration` 生成），其次是 `talkingPoints`，否则由标题、结论和要点确定性生成。
2. **语音**：在模型配置中注册带 `tts` 能力的模型并映射到 `tts` 角色（`PUT /model-routing {"role":"tts","model_config_id":…}`），系统调用兼容 OpenAI 的 `/audio/speech`。音色与格式由请求的 `voice`/`audio_format` 或 `YINGZHANG_TTS_VOICE`/`YINGZHANG_TTS_FORMAT` 决定。未配置或请求 `tts:false` 时，生成按文字长度计时的静音片段；单页合成失败只影响该页并记录在报告中。
3. **合成**：需要 `ffmpeg`（PATH 或 `YINGZHANG_FFMPEG`，不依赖 ffprobe 或 Python 封装）。每页生成参数一致的 H.264/AAC 片段，再无损拼接。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/$PID/jobs/video \
  -H 'content-type: application/json' -d '{"locale":"zh-CN","tts":true,"subtitles":true}'
# 轮询 GET /api/v1/jobs/{job_id}，完成后：
curl -o deck.mp4 http://127.0.0.1:8000/api/v1/projects/$PID/export/video
curl -o deck.srt "http://127.0.0.1:8000/api/v1/projects/$PID/export/video?subtitles=true"
```

页面预览必须与当前内容一致，否则返回 409。导出记录为 `exports` 表中 `format="mp4"` 的版本化文件，带内容指纹与 SHA-256；页面修改后旧视频不再可下载。
