"""Epoch checks also run in worker threads; a reset invalidates unpublished output."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from app.personalization.process_lock import WorkspaceLock

from fastapi import HTTPException
from sqlalchemy import select

lock = WorkspaceLock()
generation_snapshot: ContextVar[dict | None] = ContextVar("personal_generation", default=None)


@contextmanager
def project_context(project_id):
    from app.db.models import PersonalBinding
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        binding = db.get(PersonalBinding, project_id)
        snapshot = generation_snapshot.get() or (binding.snapshot if binding else None)
    token = generation_snapshot.set(snapshot)
    try:
        assert_current()
        yield
        assert_current()
    finally:
        generation_snapshot.reset(token)


def guarded_sync_generation(function):
    @wraps(function)
    def wrapped(project_id, *args, **kwargs):
        with project_context(project_id):
            return function(project_id, *args, **kwargs)

    return wrapped


def assert_current(snapshot=None):
    from app.db.models import PersonalIdentity
    from app.db.session import SessionLocal

    snapshot = snapshot if snapshot is not None else generation_snapshot.get()
    if not snapshot:
        return
    with SessionLocal() as db:
        epoch = db.scalar(
            select(PersonalIdentity.epoch).where(PersonalIdentity.id == snapshot["ownerId"])
        )
    if epoch != snapshot["epoch"]:
        raise HTTPException(409, "个人记忆已清除，本次任务上下文失效，请重新发起")


def guarded_generation(function):
    @wraps(function)
    async def wrapped(project_id, *args, **kwargs):
        from app.db.models import PersonalBinding
        from app.db.session import SessionLocal

        inherited = generation_snapshot.get()
        with SessionLocal() as db:
            binding = db.get(PersonalBinding, project_id)
            snapshot = inherited or (
                binding.snapshot if binding and function.__name__ != "_plan_project_core" else None
            )
        token = generation_snapshot.set(snapshot)
        try:
            assert_current()
            result = await function(project_id, *args, **kwargs)
            assert_current()
            return result
        finally:
            generation_snapshot.reset(token)

    return wrapped
