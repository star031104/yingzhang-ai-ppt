import base64
import hashlib
import hmac
import json
import re
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from app.config import settings
from fastapi import HTTPException, APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


COOKIE_NAME = "yingzhang_session"
router = APIRouter(prefix="/api/v1/auth", tags=["共享测试访问"])
_requests: dict[str, deque[float]] = defaultdict(deque)
_generations: dict[str, deque[float]] = defaultdict(deque)
_logins: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()


class LoginRequest(BaseModel):
    name: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=1, max_length=200)


def validate_public_config() -> None:
    if not settings.public_test_mode:
        return
    if not settings.public_test_password or len(settings.public_test_password) < 10:
        raise RuntimeError("共享测试模式需要至少 10 位测试密码")
    if not settings.public_admin_password or len(settings.public_admin_password) < 12:
        raise RuntimeError("共享测试模式需要至少 12 位管理员密码")
    if not settings.public_session_secret or len(settings.public_session_secret) < 32:
        raise RuntimeError("共享测试模式需要至少 32 位会话密钥")


def _secret() -> bytes:
    return (settings.public_session_secret or "local-development-only").encode("utf-8")


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _decode(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if int(payload.get("expires", 0)) <= int(time.time()):
        return None
    if payload.get("role") not in {"admin", "tester"}:
        return None
    return payload


def current_user(request: Request) -> dict | None:
    if settings.private_accounts_mode:
        from app.security.accounts import private_user
        return private_user(request)
    if not settings.public_test_mode:
        return {"name": "本机管理员", "role": "admin", "expires": 2**31}
    return _decode(request.cookies.get(COOKIE_NAME))


def _client_key(request: Request, user: dict) -> str:
    ip = request.headers.get("cf-connecting-ip")
    if not ip:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        ip = forwarded or (request.client.host if request.client else "unknown")
    return f"{ip}:{user.get('name', 'tester')}"


def _within_limit(bucket: dict[str, deque[float]], key: str, window: int, limit: int) -> bool:
    now = time.monotonic()
    with _rate_lock:
        entries = bucket[key]
        while entries and entries[0] <= now - window:
            entries.popleft()
        if len(entries) >= limit:
            return False
        entries.append(now)
        return True


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    expected = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlsplit(origin).netloc.lower() == expected.lower()


def _client_ip(request: Request) -> str:
    ip = request.headers.get("cf-connecting-ip")
    if not ip:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        ip = forwarded or (request.client.host if request.client else "unknown")
    return ip


def _admin_only(request: Request) -> bool:
    path, method = request.url.path, request.method.upper()
    if path.startswith(("/api/v1/providers", "/api/v1/models")):
        return True
    if path == "/api/v1/model-routing":
        return True
    if path.startswith("/api/v1/reference/"):
        return True
    if path in {"/api/v1/skills/install", "/api/v1/skills/install-url"}:
        return True
    if method == "DELETE" and path.startswith("/api/v1/skills/"):
        return True
    if method == "DELETE" and re.fullmatch(r"/api/v1/projects/[^/]+", path):
        return True
    return False


def _is_generation(request: Request) -> bool:
    if request.method.upper() != "POST":
        return False
    return bool(
        re.search(
            r"/(?:outline|sample|generate|calibrate|test-image)$|/jobs/(?:outline|sample|generate)$",
            request.url.path,
        )
    )


async def public_access_middleware(request: Request, call_next):
    path = request.url.path
    if settings.private_accounts_mode and path.startswith("/api/v1"):
        return await private_access(request, call_next)
    if not settings.public_test_mode or not path.startswith("/api/v1"):
        return await call_next(request)
    if path == "/api/v1/auth/login":
        if not _within_limit(_logins, _client_ip(request), 300, 12):
            return JSONResponse({"detail": "登录尝试过多，请五分钟后再试"}, status_code=429)
        return await call_next(request)
    if request.method.upper() == "GET" and path.startswith("/api/v1/public/decks/"):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response
    if path in {"/api/v1/health", "/api/v1/auth/session"}:
        return await call_next(request)
    user = current_user(request)
    if not user:
        return JSONResponse({"detail": "登录已失效，请重新登录"}, status_code=401)
    request.state.yingzhang_user = user
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > settings.public_upload_limit_mb * 1024 * 1024
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse(
                {"detail": f"单次上传不能超过 {settings.public_upload_limit_mb} MB"},
                status_code=413,
            )
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and not _same_origin(request):
        return JSONResponse({"detail": "请求来源校验失败"}, status_code=403)
    if user["role"] != "admin" and _admin_only(request):
        return JSONResponse({"detail": "该操作仅管理员可用"}, status_code=403)
    key = _client_key(request, user)
    if not _within_limit(
        _requests, key, 60, max(30, settings.public_rate_limit_per_minute)
    ):
        return JSONResponse({"detail": "操作过于频繁，请稍后再试"}, status_code=429)
    if _is_generation(request) and not _within_limit(
        _generations,
        key,
        600,
        max(2, settings.public_generation_limit_per_10_minutes),
    ):
        return JSONResponse({"detail": "生成次数已达到临时上限，请十分钟后再试"}, status_code=429)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@router.get("/session")
def session(request: Request):
    user = current_user(request)
    return {
        "authenticated": bool(user),
        "name": user.get("name") if user else None,
        "role": user.get("role") if user else None,
        "publicMode": settings.public_test_mode,
        "privateMode": settings.private_accounts_mode,
        "setupRequired": private_setup_required(),
    }


@router.post("/login")
def login(body: LoginRequest, request: Request):
    if settings.private_accounts_mode:
        from app.security.accounts import account_login
        return account_login(body.name, body.password, request)
    if not settings.public_test_mode:
        return {"authenticated": True, "name": "本机管理员", "role": "admin"}
    role = None
    if hmac.compare_digest(body.password, settings.public_admin_password or ""):
        role = "admin"
    elif hmac.compare_digest(body.password, settings.public_test_password or ""):
        role = "tester"
    if not role:
        return JSONResponse({"detail": "访问密码不正确"}, status_code=401)
    name = re.sub(r"[^\w\u4e00-\u9fff· -]", "", body.name).strip()[:30]
    if len(name) < 2:
        return JSONResponse({"detail": "请输入至少两个字符的测试者名称"}, status_code=422)
    expires = int(time.time()) + settings.public_session_hours * 3600
    response = JSONResponse({"authenticated": True, "name": name, "role": role})
    response.set_cookie(
        COOKIE_NAME,
        _encode({"name": name, "role": role, "expires": expires}),
        max_age=settings.public_session_hours * 3600,
        httponly=True,
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    from app.security.accounts import COOKIE
    token = request.cookies.get(COOKIE)
    if token:
        from app.db.session import SessionLocal
        from app.db.models import PersonalSession
        with SessionLocal() as db:
            row = db.get(PersonalSession, hashlib.sha256(token.encode()).hexdigest())
            if row:
                db.delete(row)
                db.commit()
    response.delete_cookie(COOKIE, path="/")
    return response


def private_setup_required():
    if not settings.private_accounts_mode:
        return False
    from app.db.session import SessionLocal
    from app.db.models import PersonalAccount
    from sqlalchemy import select
    with SessionLocal() as db:
        return db.scalar(select(PersonalAccount.id)) is None


async def private_access(request, call_next):
    from app.security.accounts import owner_context, authorize_project
    from app.db.session import SessionLocal
    from app.db.models import Job, EvaluationRun
    from sqlalchemy import select
    path = request.url.path
    # Do not trust forwarded host headers for private session CSRF checks.
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower() and origin not in settings.cors_origin_list:
        return JSONResponse({"detail": "请求来源校验失败"}, status_code=403)
    if path in {"/api/v1/auth/login", "/api/v1/auth/accounts"}:
        if not _within_limit(_logins, request.client.host if request.client else "unknown", 300, 12):
            return JSONResponse({"detail": "尝试过多，请稍后重试"}, status_code=429)
        return await call_next(request)
    if path in {"/api/v1/health", "/api/v1/auth/session"} or (request.method == "GET" and path.startswith("/api/v1/public/decks/")):
        return await call_next(request)
    user = current_user(request)
    if not user:
        return JSONResponse({"detail": "请登录独立账号"}, status_code=401)
    if user["role"] != "admin" and _admin_only(request) and not re.fullmatch(r"/api/v1/projects/[^/]+", path):
        return JSONResponse({"detail": "该操作仅管理员可用"}, status_code=403)
    context = owner_context.set(user["id"])
    request.state.yingzhang_user = user
    try:
        with SessionLocal() as db:
            match = re.match(r"/api/v1/projects/([^/]+)", path)
            if match:
                authorize_project(db, match[1], user["id"])
            match = re.match(r"/api/v1/jobs/([^/]+)", path)
            if match:
                job = db.get(Job, match[1])
                authorize_project(db, job.project_id if job else None, user["id"])
            match = re.match(r"/api/v1/evaluations/blind/([^/]+)", path)
            if match:
                evaluation = db.scalar(select(EvaluationRun).where(EvaluationRun.blind_token == match[1]))
                authorize_project(db, evaluation.project_id if evaluation else None, user["id"])
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    finally:
        owner_context.reset(context)
