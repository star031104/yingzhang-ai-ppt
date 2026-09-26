"""Reject oversized request bodies before Starlette parses multipart uploads."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import settings

ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]], Awaitable[None]]
MAX_LOCAL_REQUEST_BYTES = 110 * 1024 * 1024


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = (
            max(1, settings.public_upload_limit_mb) * 1024 * 1024
            if settings.public_test_mode
            else MAX_LOCAL_REQUEST_BYTES
        )
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    await self._reject(send, limit)
                    return
            except ValueError:
                await self._reject(send, limit)
                return

        received = 0
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as body:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                chunk = message.get("body", b"")
                received += len(chunk)
                if received > limit:
                    await self._reject(send, limit)
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break

            body.seek(0)
            replayed = 0
            sent_empty_body = False

            async def replay_receive():
                nonlocal replayed, sent_empty_body
                if replayed < received:
                    chunk = body.read(min(64 * 1024, received - replayed))
                    replayed += len(chunk)
                    return {
                        "type": "http.request",
                        "body": chunk,
                        "more_body": replayed < received,
                    }
                if received == 0 and not sent_empty_body:
                    sent_empty_body = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send, limit: int) -> None:
        body = json.dumps(
            {"detail": f"请求体超过 {limit // (1024 * 1024)} MB 限制"},
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": body})
