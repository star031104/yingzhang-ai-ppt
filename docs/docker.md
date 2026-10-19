# 映章：Docker 部署

容器镜像面向单实例部署，与本机运行使用同一套代码、迁移和质量门禁。

## 构建与启动

```bash
docker compose up -d --build
docker compose ps          # 健康状态由 /api/v1/health 决定
docker compose logs -f
```

打开 `http://127.0.0.1:8000`，在“模型配置”页面填写模型服务。Compose 只绑定本机回环地址；对局域网或公网开放前，请配置 HTTPS 反向代理、访问控制与防火墙，并阅读 README 中的安全说明。

不使用 Compose 时：

```bash
docker build -t yingzhang .
docker run -d --name yingzhang --hostname yingzhang --shm-size 1g \
  -p 127.0.0.1:8000:8000 -v yingzhang-runtime:/app/runtime yingzhang
```

## 镜像组成

| 阶段 | 内容 |
| --- | --- |
| `node-build` | `npm ci`、构建 `apps/web/dist`，再裁剪为生产依赖（PptxGenJS、Playwright 等） |
| `runtime` | Python 3.12 slim、uv（按 `uv.lock` 安装，无开发依赖）、Node 运行时、Playwright Chromium 及系统库、Noto CJK 字体、ffmpeg |

构建参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `INSTALL_LIBREOFFICE` | `false` | 安装 `libreoffice-impress`，用于 PPTX→PDF 往返检查（镜像体积显著增加） |
| `INSTALL_FFMPEG` | `true` | 讲解视频导出所需 |
| `INSTALL_OCR` | `false` | 安装 Tesseract 与简体中文语言包，用于扫描件识别 |

Compose 中可用 `YINGZHANG_INSTALL_LIBREOFFICE=true docker compose build` 开启 LibreOffice。

## 数据与凭据

- 所有持久数据都在卷 `/app/runtime`：`data/`（SQLite，WAL 模式）、`artifacts/`（材料与导出）、`secrets/`（加密凭据回退文件）、`skills/`（安装与生成的技能）。
- 容器内没有系统密钥环，模型 API Key 写入加密回退文件。默认密钥派生自主机名，因此 Compose 固定了 `hostname: yingzhang`；更推荐在 `.env` 中设置稳定的 `YINGZHANG_VAULT_KEY`。更换该值后需要重新填写模型凭据。
- 备份时先停止容器，再备份整个卷；不要只复制数据库文件。
- 使用宿主机目录挂载 `/app/runtime` 时，目录需对 UID 1000 可写。

## 运行约束

- 镜像只启动一个 Uvicorn worker；不要设置 `WEB_CONCURRENCY` 或扩容副本，任务执行器和 SQLite 写入都是单进程设计。
- 启动时自动执行 Alembic 迁移（`YINGZHANG_MIGRATE_ON_STARTUP=true`）。
- Chromium 渲染需要较大的共享内存，Compose 已设置 `shm_size: 1gb`。
- 所有 `YINGZHANG_*`（及兼容的 `SLIDEFORGE_*`）环境变量都可在 Compose 的 `environment` 中设置。
- MCP 服务器在宿主机运行，把 `YINGZHANG_API_URL` 指向映射端口即可，见 [Agent 集成说明](integrations.md)。
