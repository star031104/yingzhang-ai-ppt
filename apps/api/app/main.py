from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.security.accounts import router as accounts_router
from app.api.asset_routes import router as asset_router
from app.api.delivery_routes import router as delivery_router
from app.api.governance_routes import router as governance_router
from app.api.personal_experience_routes import router as experience_router
from app.api.personal_quality_routes import router as personal_quality_router
from app.api.personalization_routes import router as personalization_router
from app.api.project_workspace_routes import router as project_workspace_router
from app.api.quality_routes import router as quality_router
from app.api.routes import router
from app.api.skill_routes import router as skill_router
from app.api.slide_routes import router as slide_router
from app.api.slide_version_routes import router as slide_version_router
from app.api.source_routes import router as source_router
from app.api.workflow_routes import router as workflow_router
from app.config import settings
from app.db.session import create_schema
from app.jobs.manager import job_manager
from app.security.public_access import (
    public_access_middleware,
    validate_public_config,
)
from app.security.public_access import (
    router as public_access_router,
)
from app.skills.catalog import seed_visual_skill_catalog


@asynccontextmanager
async def lifespan(_):
    if settings.private_accounts_mode and settings.public_test_mode:
        raise RuntimeError("独立账号模式不能与共享测试模式同时启用")
    validate_public_config()
    create_schema()
    seed_visual_skill_catalog()
    job_manager.recover_interrupted()
    yield


app = FastAPI(
    title="映章 API",
    description="把材料变成有章法的演示",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.public_test_mode else "/docs",
    redoc_url=None if settings.public_test_mode else "/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(personalization_router)
app.include_router(accounts_router)
app.include_router(experience_router)
app.include_router(personal_quality_router)
app.include_router(asset_router)
app.include_router(delivery_router)
app.include_router(governance_router)
app.include_router(quality_router)
app.include_router(project_workspace_router)
app.include_router(slide_version_router)
app.include_router(slide_router)
app.include_router(skill_router)
app.include_router(source_router)
app.include_router(workflow_router)
app.include_router(public_access_router)
app.middleware("http")(public_access_middleware)

web_root = settings.web_dist_root.resolve()
if web_root.is_dir():
    assets = web_root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="web-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def web_app(full_path: str):
        candidate = (web_root / full_path).resolve()
        if candidate.is_file() and web_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(web_root / "index.html", headers={"Cache-Control": "no-store"})
