"""Private accounts are distinct from the legacy shared tester password."""
import hashlib
import hmac
import ipaddress
import re
import secrets
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.config import settings
from app.db.models import PersonalAccount, PersonalIdentity, PersonalSession, Project, ProjectOwner
from app.db.session import SessionLocal, get_db
from app.personalization.runtime import lock

owner_context: ContextVar[str | None] = ContextVar("private_owner", default=None)
COOKIE = "yingzhang_private_session"
router = APIRouter(prefix="/api/v1/auth")


def password_digest(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"{salt}:{key.hex()}"


def private_user(request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with SessionLocal() as db:
        session = db.get(PersonalSession, hashlib.sha256(token.encode()).hexdigest())
        if not session or session.expires_at <= datetime.now(UTC).replace(tzinfo=None):
            return None
        account = db.get(PersonalAccount, session.owner_id)
        if not account or not account.enabled:
            return None
        return {"id": account.id, "name": account.username, "role": account.role}


def account_login(name, password, request):
    with SessionLocal() as db:
        account = db.scalar(select(PersonalAccount).where(PersonalAccount.username == name.strip().casefold()))
        if not account or not account.enabled or not hmac.compare_digest(
            account.password_hash, password_digest(password, account.password_hash.split(":")[0])
        ):
            raise HTTPException(401, "账号或密码不正确")
        raw = secrets.token_urlsafe(40)
        db.execute(delete(PersonalSession).where(PersonalSession.expires_at < datetime.now(UTC).replace(tzinfo=None)))
        db.add(PersonalSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), owner_id=account.id,
                              expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=settings.public_session_hours)))
        db.commit()
        response = JSONResponse({"authenticated": True, "name": account.username, "role": account.role,
                                 "privateMode": True, "publicMode": False})
        response.set_cookie(COOKIE, raw, httponly=True, secure=settings.private_cookie_secure or request.url.scheme == "https", samesite="strict",
                            max_age=settings.public_session_hours * 3600, path="/")
        return response


def authorize_project(db, project_id, owner_id=None):
    if not settings.private_accounts_mode:
        return
    owner_id = owner_id or owner_context.get()
    binding = db.get(ProjectOwner, project_id)
    if not owner_id or not binding or binding.owner_id != owner_id:
        raise HTTPException(404, "项目不存在或不属于当前账号")


class AccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=12, max_length=200)
    claim_local_workspace: bool = False


@router.post("/accounts", status_code=201)
def create_account(body: AccountCreate, request: Request, db=Depends(get_db)):
    if not settings.private_accounts_mode:
        raise HTTPException(409, "请先在部署配置中启用独立账号模式")
    with lock:
        existing = db.scalar(select(PersonalAccount.id))
        user = private_user(request)
        if existing:
            if not user or user["role"] != "admin":
                raise HTTPException(403, "只有管理员可以创建账号")
        else:
            try:
                local = ipaddress.ip_address(request.client.host).is_loopback
            except (ValueError, AttributeError):
                local = False
            if request.headers.get("x-forwarded-for") or request.headers.get("forwarded") or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                local = False
            if not local:
                raise HTTPException(403, "首次设置请从服务器本机访问")
        name = body.name.strip().casefold()
        if not re.fullmatch(r"[\w\u4e00-\u9fff. -]{2,30}", name):
            raise HTTPException(422, "账号名称包含不支持的字符")
        if db.scalar(select(PersonalAccount.id).where(PersonalAccount.username == name)):
            raise HTTPException(409, "账号名称已存在")
        if body.claim_local_workspace and existing:
            raise HTTPException(422, "只有首次管理员设置可以接管原本机工作区")
        identity = db.scalar(select(PersonalIdentity)) if body.claim_local_workspace else None
        if not identity:
            identity = PersonalIdentity()
            db.add(identity)
            db.flush()
        account = PersonalAccount(id=identity.id, username=name, password_hash=password_digest(body.password),
                                  role="tester" if existing else "admin")
        db.add(account)
        if body.claim_local_workspace:
            for project_id in db.scalars(select(Project.id)):
                if not db.get(ProjectOwner, project_id):
                    db.add(ProjectOwner(project_id=project_id, owner_id=account.id))
        db.commit()
        return {"id": account.id, "name": account.username, "role": account.role}


@router.get("/accounts")
def list_accounts(request: Request, db=Depends(get_db)):
    user = private_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(403, "只有管理员可以管理账号")
    return [{"id": row.id, "name": row.username, "role": row.role, "enabled": row.enabled}
            for row in db.scalars(select(PersonalAccount))]


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


@router.post("/password")
def change_password(body: PasswordChange, request: Request, db=Depends(get_db)):
    user = private_user(request)
    if not user:
        raise HTTPException(401, "请登录")
    account = db.get(PersonalAccount, user["id"])
    if not hmac.compare_digest(account.password_hash, password_digest(body.current_password, account.password_hash.split(":")[0])):
        raise HTTPException(403, "当前密码不正确")
    account.password_hash = password_digest(body.new_password)
    db.execute(delete(PersonalSession).where(PersonalSession.owner_id == account.id))
    db.commit()
    return {"message": "密码已更新，全部旧登录已失效，请重新登录"}


@router.post("/accounts/{account_id}/disable")
def disable_account(account_id: str, request: Request, db=Depends(get_db)):
    user = private_user(request)
    if not user or user["role"] != "admin" or account_id == user["id"]:
        raise HTTPException(403, "管理员只能停用其他账号")
    account = db.get(PersonalAccount, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    account.enabled = False
    db.execute(delete(PersonalSession).where(PersonalSession.owner_id == account_id))
    db.commit()
    return {"status": "disabled"}
