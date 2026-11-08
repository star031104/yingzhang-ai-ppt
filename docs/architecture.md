# 映章：当前工程架构

本文描述仓库当前实现，供维护、排错和扩展使用。历史阶段性方案已由 Git 历史保存；修改架构时应同步更新本文，而不是新增只写一句结论的版本文档。

## 系统边界

映章是本地优先的单实例演示生产系统。浏览器工作台通过 `/api/v1` 访问 FastAPI；API 使用 SQLite 保存项目、材料索引、页面、任务和审批状态，文件产物位于 `runtime/`。模型与外部素材服务通过受控 Provider 边界访问。页面渲染由 Node 演示引擎承担，HTML/PDF/PPTX 共享页面内容和布局契约。

```text
材料 / 需求
  → 文档解析与来源登记
  → 证据选择、叙事规划、页面契约
  → 页面候选生成与浏览器场景测量
  → 内容、几何和视觉质量检查
  → 人工选择 / 编辑 / 审批
  → HTML、PDF、可编辑 PPTX
```

| 目录 | 职责 |
| --- | --- |
| `apps/web/src/features/` | 按创建、项目、模型、技能和个人设置组织界面 |
| `apps/web/src/api/` | 类型、HTTP 传输、项目接口、模型与技能接口 |
| `apps/api/app/api/` | HTTP 输入、权限与结果封装；路由只组合 `workflows/` 中的业务操作（`workflow_routes.py` 保留旧名称的兼容导出） |
| `apps/api/app/documents/`、`sources/`、`intelligence/` | 材料解析、来源定位和证据提取 |
| `apps/api/app/presentation_intelligence/` | 叙事规划、布局意图和候选决策 |
| `apps/api/app/workflows/`、`jobs/` | 有界任务、持久化快照、恢复和进度事件；大纲（`outline.py`、`model_planning.py`）、生成（`generation.py`）、配图、视觉反思、引导采集（`intake.py`）与排练（`rehearsal.py`）的业务实现 |
| `apps/api/app/validation/`、`evaluation/` | 完整性、视觉质量、交付和基准评估 |
| `apps/api/app/db/`、`alembic/`、`artifacts/` | 数据模型、前向迁移与文件产物 |
| `apps/api/app/security/`、`providers/` | 身份、请求边界、凭据和模型网关 |
| `packages/presentation-engine/` | 浏览器预览、场景、PDF 和原生 PPTX 导出 |
| `apps/api/app/delivery_media/` | 讲稿、语音合成（`tts` 角色）与 ffmpeg 讲解视频导出 |
| `integrations/` | stdio MCP 服务器与 Agent Skill，均只通过 REST API 访问系统 |
| `packages/scene-schema/`、`skill-schema/` | 跨模块场景和视觉技能约束 |

## 核心数据与生成流程

项目和材料在数据库中记录身份、状态与关联；上传原件、预览和导出文件保存在产物目录。解析时保留章节、表格、数字单位和来源位置。规划阶段将受众、目标、材料证据和页数预算变为逐页主张与布局契约；生成阶段只对契约允许的内容创建候选，避免把没有来源的数字包装成事实。

页面先在 HTML/CSS 中形成可测量场景，浏览器计算后的几何数据作为渲染依据。图表、表格和结构图优先导出为可编辑对象；无法等价表达的视觉元素才作为图片保留。

PPTX 默认由场景驱动编译（`YINGZHANG_PPTX_MODE=scene`，兼容 `SLIDEFORGE_PPTX_MODE`；设为 `legacy` 回到按版式手写坐标的旧编译器）。每个候选在 Chromium 中测量时额外记录导出层（`scene-export-v1`：背景/边框/圆角/阴影/渐变形状、带样式的文字段、图片、表格、图表模型、矢量图标与媒体，按绘制顺序排列；伪元素会被实体化后测量）。导出时按 1280 px = 13.333 in 把所选候选的导出层编译为原生文本框、形状、表格和图表；场景缺失、渲染指纹过期时现场重新测量，若文字覆盖或去重校验失败、图片无法定位原文件，则该页单独回退到旧编译器，原因写入导出报告 `*.export.json`。图表模型（柱/条/折线/面积/环形/散点/柱线组合/瀑布）由数据形态确定性选择，HTML 用 SVG 绘制，PPTX 使用同一绘图区布局生成原生图表。视觉技能的 `tokens.json` 可声明版式语法（网格、字号阶梯、密度、装饰母题、标题样式、图表样式、图标样式与禁用模式），旧技能不受影响。质量门禁检查证据覆盖、文字溢出、重叠、可读性和交付产物一致性。用户选择的候选与页面修订版本参与渲染指纹，旧候选不能在修改后被误用。

## 结构化输出、逐页修版与风格连续性

模型调用的 JSON 输出统一走 `providers/structured.py`：先用 `response_format=json_schema`（strict）；不合格时把模型自己的输出与逐条校验错误发回修复一次；仍失败才用宽松解析兜底。每次调用走了哪条路径按模型记账（`/api/v1/model-diagnostics/structured-output`），模型配置页显示一次通过率；服务商拒绝 schema 时会记住并改用 JSON 模式。

整稿渲染时每页运行有上限的“渲染 → 检查 → 修补”闭环（`presentation_engine/page_repair.py`，`YINGZHANG_PAGE_REPAIR_ROUNDS`，默认 2 轮）。没有安全候选时，规则把多出的要点或超长要点的后半句移入讲稿（带“不含、试点、口径”等限定词的后半句不拆）、排除测量不合格的版式、移除丢失的图片后重渲染；配置了视觉评审模型时，规则已通过的页面再由截图检查一次断行和字号。人工改过文案的页面（`contentLocked`）只调整版式，不动文字。修补记录写入 `renderRepair`，涉及文案的修补生成新的页面版本。

大纲阶段为整套稿生成一份风格契约（`presentation_intelligence/style_contract.py`：主色、字体、密度区间、深色页预算、相邻页留白与明暗跳变上限）。整稿选版时按页序把每个候选的截图明暗与占用率和上一页比较（`styleContinuity`），只在分差不大时换成更连贯的安全候选；人工选择不受影响。

## 材料知识库与检索

解析结果组织为三层知识库（`intelligence/knowledge_base.py`，`GET /projects/{id}/knowledge`）：资料卡（每份材料的结构、关键指标、发现与局限，有长度上限，规划模型先读它）、原子事实（证据图中的句子及出处）与检索块。BM25 与可选向量经 RRF 融合后，再沿标题树传播得分（父标题 0.3、最佳子标题 0.2），命中章节下的段落更容易进入证据窗口。

PDF 可选用本机文档解析模型（`documents/backends.py`：MinerU、PaddleOCR-VL 或自定义命令，`YINGZHANG_DOCUMENT_PARSER`）。默认只在扫描页、公式或无法恢复的表格出现时调用；失败时保留内置解析结果。解析出的 `$…$` 公式统一为 `$$…$$`。

## 公式

页面文字中的 `$$LaTeX$$` 由 `documents/latex_math.py`（受支持的 LaTeX 子集）转为 MathML 交给 Chromium 绘制，场景导出保留 LaTeX 源，PPTX 导出后由 `powerpoint/equations.py` 改写为 PowerPoint 原生公式（OMML，带可读的 Unicode 线性文本回退）。不支持的写法保持原文，不会变成错误公式。LibreOffice 24.x 会同时显示公式对象与回退文本；面向 LibreOffice 时可设 `YINGZHANG_PPTX_EQUATIONS=linear`。

## 后台任务与恢复

`JobManager` 对外提供统一任务视图。`JobStore` 使用 SQLite 持久化完整快照；本地执行器运行异步任务，内存事件总线仅负责实时通知。浏览器先读取任务快照，再订阅 SSE/WebSocket；断线时可轮询，因此事件丢失不会改变任务真实状态。

项目生成使用有输入/输出约束的有界节点。每个节点记录幂等键、尝试次数、产物和检查点；服务重启后仅恢复具有完整重建上下文的任务。取消在安全边界协作完成，页面保存通过修订号阻止过期写入。当前执行器只支持一个服务进程和一个实例，多实例部署需要共享队列、租约和事件设施，不能直接增加 Uvicorn worker 数。

## 安全与数据边界

本地模式默认把工作区留在当前设备。独立账号模式下，项目读取、上传、修改、审批和发布由服务端校验；公网测试模式另有会话、限额和请求大小约束。Provider 凭据保存在系统密钥环或本地加密回退文件，不进入 SQLite。下载外部素材和技能前需经过地址、类型与大小检查；第三方技能默认不执行脚本。

`runtime/`、`.env`、生成结果和用户材料不进入版本控制。迁移是前向的：`apps/api/alembic/versions/` 中每个版本都属于当前升级路径，不能当作“旧版本代码”删除。升级已有工作区前应备份数据库与产物目录。

## 验证与扩展约束

- Python：`uv sync --locked --extra dev`，随后运行 Ruff、Pytest 和 `scripts/verify-benchmarks.py`。
- Web/引擎：`npm ci`，运行 `npm run test:web`、`npm run test:engine`、`npm run build`。
- CI：从空白 SQLite 执行迁移，并用 LibreOffice 对四类基准演示做 PPTX→PDF 往返检查；`scripts/verify-office-roundtrip.py` 同时把 PPTX 渲染页与所选 HTML 候选截图比较，输出逐页跨格式保真度（场景模式与旧模式对照）。
- 评测：`faithfulness`（逐条主张回查原文、图文对齐）与 `drift`（多轮编辑越界修改、人工决定是否被覆盖）可通过 `POST /projects/{id}/evaluations` 运行；基准门禁另含扰动测试，要求每个质量门禁都能拦住注入的对应缺陷。
- 参考模板基准由 `benchmarks/reference-style/build_template.py` 合成，自动检查模板语法学习、母版版式路由与母版保真。
- `scripts/verify-office-roundtrip.py --mode compare` 用同一批 HTML 候选对比场景编译器、旧编译器与独立开源实现 dom-to-pptx 的跨格式保真度。
- `scripts/update-doc-stats.py --check` 保证文档中的测试数量与代码一致。
- 外部交付：重要内容仍需人工核对事实、许可、品牌和目标 Office/WPS 环境中的排版。

新增能力时应保持 API 权限、任务恢复、页面修订号、渲染指纹和导出检查一致；不要让前端状态或模型回复成为绕过这些约束的第二套事实来源。
