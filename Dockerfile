# syntax=docker/dockerfile:1.7
# 映章 YingZhang — single-instance local deployment image.
#
#   docker build -t yingzhang .
#   docker build --build-arg INSTALL_LIBREOFFICE=true -t yingzhang:office .
#
# The built-in job executor is single-process: the image runs exactly one
# uvicorn worker. Persist /app/runtime (database, artifacts, secrets, skills).

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.8.17

# ---------- Node: web build + production engine dependencies ----------
FROM node:${NODE_VERSION}-bookworm-slim AS node-build
WORKDIR /src
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    npm_config_fund=false \
    npm_config_audit=false
COPY package.json package-lock.json .npmrc ./
COPY apps/web/package.json apps/web/package.json
COPY packages/presentation-engine/package.json packages/presentation-engine/package.json
COPY packages/scene-schema/package.json packages/scene-schema/package.json
COPY packages/skill-schema/package.json packages/skill-schema/package.json
RUN npm ci
COPY apps/web apps/web
COPY packages packages
RUN npm run build \
    && npm prune --omit=dev

# ---------- uv binary ----------
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------- Runtime: Python 3.12 + Node + Chromium + CJK fonts ----------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ARG INSTALL_LIBREOFFICE=false
ARG INSTALL_FFMPEG=true
ARG INSTALL_OCR=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/app/.venv/bin:$PATH \
    YINGZHANG_DATABASE_URL=sqlite:////app/runtime/data/yingzhang.db \
    YINGZHANG_ARTIFACT_ROOT=/app/runtime/artifacts \
    YINGZHANG_WEB_DIST_ROOT=/app/apps/web/dist

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=node-build /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

RUN set -eux; \
    apt-get update; \
    packages="fonts-noto-cjk fonts-noto-color-emoji fontconfig ca-certificates libstdc++6"; \
    if [ "$INSTALL_FFMPEG" = "true" ]; then packages="$packages ffmpeg"; fi; \
    if [ "$INSTALL_LIBREOFFICE" = "true" ]; then packages="$packages libreoffice-impress"; fi; \
    if [ "$INSTALL_OCR" = "true" ]; then packages="$packages tesseract-ocr tesseract-ocr-chi-sim"; fi; \
    apt-get install -y --no-install-recommends $packages; \
    rm -rf /var/lib/apt/lists/*

# Python dependencies from the lock file (no dev extras).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Node runtime dependencies, then Playwright Chromium and its system libraries.
COPY --from=node-build /src/node_modules node_modules
COPY --from=node-build /src/package.json /src/package-lock.json ./
RUN set -eux; \
    node node_modules/playwright/cli.js install --with-deps chromium; \
    rm -rf /var/lib/apt/lists/* /tmp/*

# Application source and the built web UI.
COPY apps/api apps/api
COPY packages packages
COPY skills/visual skills/visual
COPY integrations integrations
COPY --from=node-build /src/apps/web/dist apps/web/dist

# Everything that must survive container replacement lives under /app/runtime.
RUN set -eux; \
    useradd --create-home --uid 1000 --shell /usr/sbin/nologin yingzhang; \
    mkdir -p runtime; \
    ln -s /app/runtime/secrets /app/.yingzhang; \
    ln -s /app/runtime/skills/installed /app/skills/installed; \
    ln -s /app/runtime/skills/generated /app/skills/generated; \
    chown -R yingzhang:yingzhang /app/runtime /app/skills; \
    chmod -R a+rX /ms-playwright

USER yingzhang
VOLUME ["/app/runtime"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

# One worker only: the job executor and SQLite writer are per-process.
CMD ["sh", "-c", "mkdir -p runtime/data runtime/artifacts runtime/secrets runtime/skills/installed runtime/skills/generated && exec python -m uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000 --workers 1"]
