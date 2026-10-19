"""Serialized, retried SQLite writes for job progress and checkpoints.

SQLite allows one writer at a time. Job progress is written from the event-loop
thread while generation code may briefly hold a write transaction elsewhere, so
a plain ``UPDATE jobs`` can fail with ``database is locked``. Job writes here:

* run under one process-wide writer lock, so job-store writes never race each other;
* use a short per-attempt busy timeout in async code, so a blocked attempt does not
  freeze the event loop for the full connection timeout;
* retry the whole read-modify-write unit with exponential backoff.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from app.db.session import SQLITE_BUSY_TIMEOUT_MS, SessionLocal, engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

T = TypeVar("T")

JOB_WRITE_LOCK = threading.RLock()
WRITE_ATTEMPTS = 10
BASE_DELAY_SECONDS = 0.05
MAX_DELAY_SECONDS = 2.0
ASYNC_ATTEMPT_BUSY_TIMEOUT_MS = 2000
_LOCK_MARKERS = ("database is locked", "database table is locked", "database is busy")


def is_sqlite_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, OperationalError | sqlite3.OperationalError):
        return False
    text = str(getattr(exc, "orig", None) or exc).lower()
    return any(marker in text for marker in _LOCK_MARKERS)


def backoff_delay(attempt: int) -> float:
    return min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2**attempt))


def _set_busy_timeout(connection, milliseconds: int) -> None:
    connection.exec_driver_sql(f"PRAGMA busy_timeout={int(milliseconds)}")
    connection.commit()


def _attempt(write: Callable[[Session], T], busy_timeout_ms: int | None) -> T:
    sqlite = engine.dialect.name == "sqlite"
    with JOB_WRITE_LOCK:
        if not sqlite or not busy_timeout_ms:
            with SessionLocal() as db:
                return write(db)
        # Pin one connection so the shortened timeout is restored before it
        # returns to the pool.
        with engine.connect() as connection:
            _set_busy_timeout(connection, busy_timeout_ms)
            try:
                with SessionLocal(bind=connection) as db:
                    return write(db)
            finally:
                if connection.in_transaction():
                    connection.rollback()
                _set_busy_timeout(connection, SQLITE_BUSY_TIMEOUT_MS)


def run_job_write(
    write: Callable[[Session], T], *, attempts: int = WRITE_ATTEMPTS
) -> T:
    """Run ``write(db)`` (which must commit) with the writer lock and lock retries."""
    for attempt in range(attempts):
        try:
            return _attempt(write, None)
        except OperationalError as exc:
            if not is_sqlite_lock_error(exc) or attempt == attempts - 1:
                raise
        time.sleep(backoff_delay(attempt))
    raise RuntimeError("unreachable")  # pragma: no cover


async def run_job_write_async(
    write: Callable[[Session], T], *, attempts: int = WRITE_ATTEMPTS
) -> T:
    """Async variant: short busy waits and non-blocking backoff between attempts."""
    for attempt in range(attempts):
        try:
            return _attempt(write, ASYNC_ATTEMPT_BUSY_TIMEOUT_MS)
        except OperationalError as exc:
            if not is_sqlite_lock_error(exc) or attempt == attempts - 1:
                raise
        await asyncio.sleep(backoff_delay(attempt))
    raise RuntimeError("unreachable")  # pragma: no cover
