<div align="center">

<img src="docs/assets/yingzhang-ai-ppt-cover.png" alt="映章 AI 演示生产系统" width="100%">

# 映章 · YingZhang

面向专业内容生产的本地 AI 演示工作台

[![Release](https://img.shields.io/badge/release-v0.1.0-5b55e7?style=flat-square)](https://github.com/star031104/yingzhang-ai-ppt)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-20%2B-339933?style=flat-square&logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=111827)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

从 PDF、Word、Excel、PPTX、Markdown、网页和图片中提取结构与证据，完成叙事规划、逐页生成、质量检查，并交付 HTML、PDF 与原生可编辑 PPTX。

[功能概览](#功能概览) · [快速开始](#快速开始) · [部署说明](#部署说明) · [使用指南](#使用指南) · [工程架构](docs/architecture.md) · [开发报告](docs/development-report.md)

</div>

> [!IMPORTANT]
> 当前为首个公开版本 `v0.1.0`，适合本地体验、功能验证和二次开发。重要演示在正式交付前，仍应人工核对事实、版权、排版和 Office 兼容性。

## 项目定位

映章不是一次性生成几张文字卡片的模板工具。它把演示生产拆成材料解析、证据绑定、叙事规划、页面契约、视觉候选、人工选择、定向修复和交付检查等可追踪阶段。

核心设计原则：

- **证据优先**：数字、结论、表格、原文图片与来源位置建立关联。
- **过程可控**：长任务按有界节点执行，可重试、可恢复、可审阅。
- **编辑友好**：图表、表格、时间线、流程图等优先输出为原生 PPT 对象。
- **本地优先**：项目文件、模型凭据和个性化数据默认保存在当前设备。
- **质量门禁**：生成、修复和正式导出共享同一套完整性与可读性检查。

## 功能概览

### 材料理解与证据组织

- 解析 PDF、DOCX、XLSX、CSV、PPTX、Markdown、HTML 和常见图片格式。
- 保留章节层级、表格行列、单位、图像和来源定位。
- 提取关键事实、数字声明、限制条件与可用视觉素材。
- 展示材料读取情况，提示扫描文档、缺失计算值或截断内容等风险。

### 演示规划与页面生成

- 根据受众、目标、时长、语气、品牌和演示类型规划叙事。
- 为每页建立角色、主张、证据、布局区域、文字预算和对象上限。
- 支持多种视觉设计技能，并为页面生成、评估多个候选方案。
- 支持页级并发、任务恢复、单页重生成和对象级修改。

### 专业交付

- 输出网页预览、PDF 和可编辑 PPTX。
- 支持图表、数据表、时间线、流程、层级与关系图等原生对象。
- 提供内容完整性、视觉质量、无障碍与素材许可检查。
- 支持页面版本、人工选择保护、审阅意见和发布快照。

### 本地个人助手

- 可按不同场景保存叙事与视觉偏好。
- 可从参考稿和用户确认过的修改中形成经验建议。
- 支持暂停学习、导入导出、单条遗忘、按场景清除和恢复空白工作区。
- 首次启动不会包含任何作者个人偏好；每个克隆实例从独立的本地数据开始。

## 系统架构

```mermaid
flowchart LR
    A[材料与创作要求] --> B[解析与来源登记]
    B --> C[证据与内容选择]
    C --> D[叙事与页面规划]
    D --> E[多候选页面生成]
    E --> F[质量检查与定向修复]
    F --> G[人工审阅与编辑]
    G --> H[HTML / PDF / Editable PPTX]
```

| 层级 | 主要技术 |
| --- | --- |
| Web 工作台 | React 19、TypeScript、Vite、TanStack Query、Zustand |
| API 与任务 | FastAPI、Uvicorn、Pydantic、SQLAlchemy、Alembic |
| 演示渲染 | Playwright、PptxGenJS、python-pptx |
| 文档解析 | PyMuPDF、python-docx、openpyxl、BeautifulSoup |
| 本地存储 | SQLite、系统密钥环、加密文件回退 |
| 模型接入 | OpenAI-Compatible HTTP API |

## 快速开始

### 环境要求

- Git（仅克隆项目时需要）
- Windows 10/11 可使用根目录的一键启动器；macOS 与 Linux 使用手动方式
- Windows 首次启动需要网络、Microsoft Store 中的“应用安装程序”（提供 winget）；安装运行环境时可能出现 Windows 权限提示
- 至少一个兼容 OpenAI API 的模型服务；可以是云端 API，也可以是本机服务

### Windows 一键运行

```powershell
git clone https://github.com/star031104/yingzhang-ai-ppt.git
cd yingzhang-ai-ppt
```

双击项目根目录中的 **`启动映章.exe`**。也可以双击 `启动项目.cmd`，或在终端运行：

```powershell
./启动项目.cmd
```

首次启动器会自动准备 uv 管理器、Python 3.12、Node.js LTS、锁定的 Python/npm 依赖和 Playwright Chromium，然后构建前端、启动本地服务并打开 `http://127.0.0.1:8000`。安装器需要网络；若系统没有 winget，请先从 Microsoft Store 安装“应用安装程序”。关闭浏览器不会停止后台服务；运行日志位于 `runtime/launcher/`。模型服务可在应用的模型设置中配置，无需预先创建 `.env` 文件。

`.exe` 使用项目附带的 C# 源码构建。如需重建它，请在 Windows PowerShell 运行 `./scripts/build-launcher.ps1`（需要 .NET Framework 4.x 编译器）。

如果 8000 端口已被占用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 8001
```

### 手动安装与运行

以下方式适合开发、排错，或在 macOS/Linux 上部署。

```bash
git clone https://github.com/star031104/yingzhang-ai-ppt.git
cd yingzhang-ai-ppt
python -m venv .venv
```

激活虚拟环境：

```powershell
# Windows PowerShell
./.venv/Scripts/Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

使用锁定依赖安装开发环境：

```bash
uv sync --locked --extra dev
npm ci
npx playwright install chromium
```

创建本地配置：

```powershell
# Windows
Copy-Item .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

构建网页并启动完整应用：

```bash
npm run build
uv run --locked python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

打开：

- 应用：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

## 部署说明

### 本地生产式运行

推荐先构建前端，再只运行一个 FastAPI 进程。后端会直接提供 `apps/web/dist/` 中的静态页面：

```bash
npm ci
npm run build
uv sync --locked
uv run --locked python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

应用启动时默认执行 Alembic `upgrade head`，随后核对数据库表和字段；结构不匹配时会明确停止启动，避免应用带着不完整结构运行。升级已有数据库前仍应先备份。多进程或多副本部署应在发布阶段单独执行 `python -m alembic -c apps/api/alembic.ini upgrade head`，再设置 `SLIDEFORGE_MIGRATE_ON_STARTUP=false`，避免多个服务实例同时运行迁移。0005 之后的模式快照是静态契约；未来模型变更必须新增前向迁移。

数据库与上传/生成文件需要作为一个工作区共同备份。停止应用后，使用 `python scripts/backup_workspace.py create runtime/backups/workspace.zip` 创建快照，使用 `python scripts/backup_workspace.py verify runtime/backups/workspace.zip` 校验完整性。恢复前保持应用停止，再执行 `python scripts/backup_workspace.py restore runtime/backups/workspace.zip --confirm`；恢复前会额外保存当前工作区副本。备份包请放在数据库和产物目录之外，并另行复制到安全位置。

当前内置任务执行器只支持单进程、单实例。应用会在检测到常见多 worker 配置时拒绝启动；多实例任务执行需要先部署共享队列与原子任务租约。单实例的并发执行数和等待队列容量可用 `SLIDEFORGE_MAX_CONCURRENT_JOBS` 与 `SLIDEFORGE_MAX_QUEUED_JOBS` 调整，队列满时 API 返回 503。反向代理部署时仅在应用端口禁止绕过代理直连的情况下配置 `SLIDEFORGE_TRUSTED_PROXY_IPS`，填写代理源地址或 CIDR，并使用 `uvicorn --no-proxy-headers` 保留应用所见的直接连接地址；转发头不在该信任范围内时不会用于限流识别。共享公网模式的生成限额按来源 IP 计算，治理操作仅管理员可执行。

启用独立账号后，项目成员需填写已启用账号的登录名称；项目角色会限制查看、编辑、上传、审批、发布和撤销操作。最终批准会记录当前页面数据和渲染文件的摘要，发布时必须与批准版本一致；修改后需重新审批。

默认监听 `127.0.0.1`，仅当前电脑可访问。若要提供局域网或公网访问，需要自行配置反向代理、HTTPS、访问控制和防火墙，并在公开前完整审阅安全设置。首版不建议直接裸露 Uvicorn 端口。

### 前后端开发模式

打开两个终端。终端一运行 API：

```bash
python -m uvicorn app.main:app --app-dir apps/api --reload --port 8000
```

终端二运行 Vite：

```bash
npm run dev
```

访问 `http://127.0.0.1:5173`。开发服务器会把 `/api` 请求代理到 `http://127.0.0.1:8000`。

### 配置项

复制 `.env.example` 后按需修改。常用设置如下：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SLIDEFORGE_DATABASE_URL` | `sqlite:///./runtime/data/yingzhang.db` | 本地数据库地址 |
| `SLIDEFORGE_MIGRATE_ON_STARTUP` | `true` | 启动时应用 Alembic 迁移；多副本部署应在发布阶段单独迁移并关闭 |
| `SLIDEFORGE_ARTIFACT_ROOT` | `./runtime/artifacts` | 上传材料和生成产物目录 |
| `SLIDEFORGE_CORS_ORIGINS` | 本地 5173 地址 | 开发环境允许的前端来源 |
| `SLIDEFORGE_RENDER_CONCURRENCY` | `2` | 单个演示任务同时渲染的页面数，低内存设备建议设为 1 |
| `SLIDEFORGE_MAX_CONCURRENT_JOBS` | `2` | 同时执行的后台任务数，范围 1–16 |
| `SLIDEFORGE_MAX_QUEUED_JOBS` | `6` | 后台等待任务上限，超过后 API 返回 503，范围 0–64 |
| `SLIDEFORGE_OPTIONAL_IMAGE_WAIT_SECONDS` | `45` | 可选远程配图的单轮等待时间 |
| `SLIDEFORGE_LOCAL_ONLY_MODE` | `false` | 设为 `true` 后仅允许连接本机模型服务 |
| `SLIDEFORGE_PUBLIC_TEST_MODE` | `false` | 共享公网测试模式；启动公网隧道前必须启用并配置下列凭据 |
| `SLIDEFORGE_PUBLIC_TEST_PASSWORD` | 未设置 | 测试者密码，至少 10 位 |
| `SLIDEFORGE_PUBLIC_ADMIN_PASSWORD` | 未设置 | 管理员密码，至少 12 位，且必须与测试者密码不同 |
| `SLIDEFORGE_PUBLIC_SESSION_SECRET` | 未设置 | 会话签名密钥，至少 32 位 |
| `SLIDEFORGE_PUBLIC_UPLOAD_LIMIT_MB` | `25` | 公网模式的请求体总上限；缺少 `Content-Length` 时同样生效 |
| `SLIDEFORGE_TRUSTED_PROXY_IPS` | 未设置 | 仅用于限流的可信反向代理地址/CIDR |
| `SLIDEFORGE_PRIVATE_ACCOUNTS_MODE` | `false` | 本地单用户场景保持关闭 |
| `SLIDEFORGE_OFFICE_EXECUTABLE` | 自动发现 | 可选的 LibreOffice 可执行文件路径 |
| `SLIDEFORGE_OCR_EXECUTABLE` | 自动发现 | 可选的本地 Tesseract 可执行文件路径；安装后可识别扫描 PDF 和图片 |
| `SLIDEFORGE_OCR_LANGUAGES` | `chi_sim+eng` | Tesseract 语言包；默认识别简体中文和英文 |
| `SLIDEFORGE_OCR_MAX_PAGES` | `20` | 每份 PDF 最多自动识别的扫描页数 |

不要把真实密钥写入 `.env.example`。公网测试脚本会强制启用共享测试认证，并在建立隧道前检查未登录项目请求是否返回 401；如未配置不同的测试者/管理员密码和会话密钥，脚本会拒绝启动。模型地址、API Key 和模型选择应在应用的“模型配置”页面中填写，凭据保存在当前设备。

上传限制在 HTTP 请求进入 multipart 解析之前执行，因此即使请求没有提供 `Content-Length`，也会在达到总上限时以 413 拒绝；本地模式的总请求体上限为 110 MiB，公开测试模式使用 `SLIDEFORGE_PUBLIC_UPLOAD_LIMIT_MB`。SQLite 启动连接会启用外键约束，并在启动时检查已有外键记录；发现历史不一致时会停止启动并列出待处理记录。

Python 依赖使用 `uv.lock` 锁定。安装开发依赖请运行 `uv sync --locked --extra dev`；生产运行环境使用 `uv sync --locked`，并将锁文件与代码版本一起发布。

Node 依赖使用 `package-lock.json` 锁定。PptxGenJS 4.0.1 仍声明依赖存在高危漏洞的 `image-size` 1.x，因此根目录暂时强制使用已修复的 2.0.4；PptxGenJS 当前打包代码没有调用该解析器，演示文稿导出和浏览器测试已覆盖此组合。上游更新依赖声明后应移除该覆盖；在此之前，`npm ls image-size` 可能因上游版本范围不匹配报告 `invalid`，以 `npm ci`、实际测试和 `npm audit --omit=dev --audit-level=high` 为发布检查。

## 使用指南

1. 打开“新建演示”，填写主题、受众、沟通目标、时长和风格要求。
2. 上传材料并检查读取结果，确认关键章节、数字、图表和限制条件。
3. 配置兼容 OpenAI API 的服务地址、API Key 与模型，先执行连接测试。
4. 生成并审阅大纲，确认页面顺序和每页的核心任务。
5. 生成页面候选，在编辑工作台选择版式并进行局部修改。
6. 运行质量检查，处理内容缺失、溢出、对比度、来源或许可问题。
7. 在 PowerPoint、WPS 或 LibreOffice 中复核最终文件，然后正式交付。

### 模型兼容性

模型服务需要提供 OpenAI-Compatible 接口。不同服务对模型列表、视觉输入、结构化输出和超时策略的支持并不完全相同。连接测试成功后，再用少量页面验证能力和成本。图片模型是可选项；未配置时，系统仍可使用材料原图、图表和内置视觉结构完成演示。

扫描 PDF 与图片可选用本机 Tesseract 识别。安装 Tesseract 和对应语言数据后，系统会自动查找；也可以在 `.env` 中配置可执行文件、语言和每份 PDF 的识别页数上限。原始文件留在本机处理。OCR 结果会标记为需要人工核对，尤其是数字和表格；识别文字不会被当作已验证的表格结构。

### Office 兼容性

PPTX 以原生可编辑为目标，但不同版本的 PowerPoint、WPS 和 LibreOffice 对字体、SVG、动画和文本度量存在差异。正式使用前请在目标 Office 环境中检查字体替换、换行、图表和媒体对象。

CI 会由映章生成器根据学术、商业、数据和产品四类基准材料生成 PPTX，再在 LibreOffice 中执行 PPTX→PDF 往返渲染，核对页数与每页标题。此检查不代表 PowerPoint 与 WPS 的实机验收；专业评测只有在当前内容指纹对应的导出文件已通过至少两种软件的实际渲染和人工复核后，才会报告跨平台交付成功。

## 测试与质量检查

```bash
# Python API、工作流与文档解析
uv run --locked --extra dev python -m pytest

# 前端组件
npm run test:web

# 演示生成引擎
npm run test:engine

# 前端生产构建
npm run build
```

项目还包含 `benchmarks/` 与 `test-materials/`，用于验证数据页、长文本、学术答辩和业务汇报等典型场景。测试材料只用于功能验证，不代表真实业务结论。

## 数据、安全与隐私

- `.env`、`runtime/`、`output/`、数据库、日志、个人经验、模型凭据和临时文件均不进入版本控制。
- 所有克隆实例从空白本地工作区开始，不包含维护者的账号、API Key、项目数据或个人偏好。
- Provider 凭据优先保存到操作系统密钥环；无法使用时才回退到本地加密文件。
- `SLIDEFORGE_LOCAL_ONLY_MODE=true` 可限制模型与素材请求只访问本机地址。
- 上传含敏感内容的材料前，请确认所连接模型服务的数据处理与保留政策。
- 本地运行不等于已经满足组织级安全要求；公网部署前必须补充身份认证、HTTPS、密钥管理、备份和审计策略。

如怀疑密钥曾被提交，请立即在服务商后台撤销并重新生成；仅从文件中删除并不能使旧密钥失效。

## 项目结构

```text
yingzhang-ai-ppt/
├─ apps/
│  ├─ api/                         FastAPI、工作流、解析与持久化
│  └─ web/                         React 创作工作台
├─ packages/
│  ├─ presentation-engine/         HTML、PDF 与 PPTX 生成引擎
│  ├─ scene-schema/                页面场景中间表示
│  └─ skill-schema/                视觉技能约束
├─ skills/visual/                  内置视觉设计技能
├─ benchmarks/                     渲染质量基准
├─ test-materials/                 可公开的验收材料
├─ tests/                          Python 自动化测试
├─ docs/architecture.md            当前工程架构与模块边界
├─ docs/development-report.md      项目开发报告
├─ scripts/                        启动、验证与维护脚本
├─ .env.example                    安全的配置模板
└─ 启动项目.cmd                    Windows 一键启动入口
```

## 常见问题

**页面可以打开，但生成任务失败**

先在“模型配置”中测试连接，确认 Base URL、API Key、模型名和服务额度。再检查启动终端或 `runtime/launcher/` 中的日志。

**Chromium 或页面渲染不可用**

```bash
npx playwright install chromium
```

Linux 环境若缺少系统依赖，可根据 Playwright 的提示安装依赖后重试。

**端口 8000 被占用**

将启动参数改为其他端口，例如 `8001`；使用开发模式时，也要同步调整前端代理配置。

**如何清除本机数据**

优先使用应用内的清除与遗忘功能。需要恢复完全空白的本地工作区时，请先退出服务并备份必要产物，再运行维护脚本 `scripts/reset-personal-workspace.py`。

## 当前边界

- 扫描版 PDF 尚不能保证完成可靠的文字识别。
- 复杂公式、特殊图表、第三方字体和既有 PPT 动画可能需要人工修复。
- 自动生成内容可能包含事实错误；来源绑定不能替代人工核验。
- 网络图片的版权、商标和人物授权仍由使用者最终确认。
- 首个公开版本的接口和数据结构仍可能调整，不承诺向后兼容。

## 参与开发

提交改动前，请至少运行与改动范围相关的测试，并避免提交任何真实材料、账户数据、API Key、运行数据库或生成结果。架构层面的重要变更应同步更新 [当前工程架构](docs/architecture.md)。

GitHub Actions 会在推送和 Pull Request 时运行后端测试、前端测试及生产构建。演示工作区会累计显示模型服务实际返回的输入/输出 token 数；不会保存提示词或模型回复。由于各服务商费率和计费口径不同，未配置可核对的费率前不会将 token 数换算成费用。

## 许可证

当前仓库尚未附带开源许可证。除非版权所有者另行授权，否则请勿假定代码可以复制、修改或再分发。
