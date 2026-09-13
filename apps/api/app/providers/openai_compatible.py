import base64
import asyncio
import hashlib
import json
from pathlib import Path
import ipaddress
import socket
import time
from urllib.parse import urlparse, quote

import httpx
from app.config import settings
from app.personalization.runtime import assert_current
from app.security.network_policy import ensure_network_allowed
from app.providers.image_models import image_candidates, image_model_problem


class ProviderError(RuntimeError):
    pass


class ImageGenerationPending(ProviderError):
    """A durable remote task is still running, rather than a failed request."""


def assert_public_image_url(value: str) -> None:
    host = urlparse(value).hostname
    if not host:
        raise ProviderError("生图模型返回了无效图片地址")
    for info in socket.getaddrinfo(host, None):
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ProviderError("生图模型返回的图片地址不允许访问本地网络")


class OpenAICompatibleClient:
    def __init__(self, base_url, api_key, extra_headers, timeout):
        self.base_url = base_url.rstrip("/")
        self.models_url = self.base_url + "/models"
        self.chat_url = self.base_url + "/chat/completions"
        self.headers = dict(extra_headers)
        self.timeout = timeout
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def list_models(self, model_type: str | None = None):
        try:
            ensure_network_allowed(self.models_url)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(trust_env=not settings.local_only_mode, timeout=self.timeout) as client:
                response = await client.get(
                    self.models_url,
                    headers=self.headers,
                    params={"type": model_type} if model_type else None,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(str(exc)) from exc
        items = payload.get("data", [])
        models = image_candidates(items) if model_type == "image" else [str(x["id"]) for x in items if x.get("id")]
        return models, round(
            (time.perf_counter() - started) * 1000
        )

    async def image_generation(
        self,
        model: str,
        prompt: str,
        image_size: str | None = None,
        *,
        task_state_path: Path | None = None,
        wait_seconds: float = 600,
    ) -> bytes:
        problem = image_model_problem(model)
        if problem:
            raise ProviderError(problem)
        modelscope = urlparse(self.base_url).hostname == "api-inference.modelscope.cn"
        payload = {"model": model, "prompt": prompt}
        if image_size:
            if "siliconflow" in self.base_url.lower():
                payload["image_size"] = image_size
            elif modelscope:
                payload["size"] = image_size
            else:
                payload["size"] = "1536x1024" if image_size != "1024x1024" else image_size
        pending_saved = False
        try:
            assert_current()
            ensure_network_allowed(self.base_url)
            fingerprint = hashlib.sha256(json.dumps([self.base_url, payload], sort_keys=True).encode()).hexdigest()
            data = {}
            if modelscope and task_state_path and task_state_path.is_file():
                try:
                    saved = json.loads(task_state_path.read_text(encoding="utf-8"))
                    if saved.get("fingerprint") == fingerprint and saved.get("task_id") and saved.get("status") not in {"FAILED", "CANCELED", "CANCELLED"} and time.time() - saved.get("created", 0) < 86400:
                        data = {"task_id": saved["task_id"]}
                        pending_saved = True
                except (ValueError, OSError, TypeError):
                    pass
            async with asyncio.timeout(wait_seconds), httpx.AsyncClient(trust_env=not settings.local_only_mode, timeout=max(self.timeout, 60.0)) as client:
                if not data:
                    response = await client.post(
                        self.base_url + "/images/generations",
                        headers={**self.headers, **({"X-ModelScope-Async-Mode": "true"} if modelscope else {})},
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    if modelscope and data.get("task_id") and task_state_path:
                        assert_current()
                        task_state_path.parent.mkdir(parents=True, exist_ok=True)
                        task_state_path.write_text(json.dumps({"fingerprint": fingerprint, "task_id": data["task_id"], "created": time.time(), "status": "PENDING"}), encoding="utf-8")
                        pending_saved = True
                if modelscope and data.get("task_id"):
                    task_url = self.base_url + "/tasks/" + quote(str(data["task_id"]), safe="")
                    while True:
                        assert_current()
                        response = await client.get(task_url, headers={**self.headers, "X-ModelScope-Task-Type": "image_generation"})
                        response.raise_for_status()
                        data = response.json()
                        status = str(data.get("task_status", "")).upper()
                        if status == "SUCCEED":
                            data = {"images": [{"url": url} if isinstance(url, str) else url for url in data.get("output_images", [])]}
                            break
                        if status in {"FAILED", "CANCELED", "CANCELLED"}:
                            if task_state_path:
                                task_state_path.unlink(missing_ok=True)
                            raise ProviderError("魔搭生图任务失败：" + self._safe_error(data))
                        await asyncio.sleep(2)
                images = data.get("images") or data.get("data") or []
                if not images:
                    raise ProviderError("生图模型没有返回图片")
                item = images[0]
                encoded = item.get("b64_json")
                if encoded:
                    return base64.b64decode(encoded)
                url = item.get("url")
                if not url:
                    raise ProviderError("生图模型返回缺少图片地址")
                if settings.local_only_mode:
                    ensure_network_allowed(url)
                else:
                    assert_public_image_url(url)
                image = await client.get(url)
                image.raise_for_status()
                assert_current()
                return image.content
        except ProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            try:
                detail = self._safe_error(exc.response.json())
            except ValueError:
                detail = "服务未返回可读的错误原因，请检查模型 ID、权限和参数"
            raise ProviderError(f"服务返回 HTTP {exc.response.status_code}：{detail}") from exc
        except TimeoutError as exc:
            if pending_saved:
                raise ImageGenerationPending(f"已等待 {wait_seconds:g} 秒，服务仍在生成；任务已保存，继续查询即可，无需重新提交") from exc
            hint = "；任务已保存，再次测试或重试将继续查询" if task_state_path and task_state_path.is_file() else "；请稍后重试"
            raise ProviderError(f"配图仍未在 {wait_seconds:g} 秒内完成{hint}") from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise ProviderError(detail) from exc

    def _safe_error(self, data):
        if not isinstance(data, dict):
            return "服务返回了无法识别的错误，请检查模型 ID、权限和参数"
        value = data.get("errors") or data.get("error") or data.get("message") or data.get("task_status") or "请求未成功"
        if isinstance(value, dict):
            value = value.get("message") or value.get("msg") or value.get("code") or "请求未成功"
        value = str(value)
        for secret in self.headers.values():
            if isinstance(secret, str) and len(secret) > 8:
                value = value.replace(secret, "[已隐藏]")
                if secret.startswith("Bearer "):
                    value = value.replace(secret[7:], "[已隐藏]")
        return value[:600]

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.25,
        max_tokens: int = 6000,
        json_mode: bool = False,
        thinking_budget: int | None = None,
        json_schema: dict | None = None,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": json_schema}}
        if thinking_budget is not None:
            payload["thinking_budget"] = thinking_budget
        try:
            assert_current()
            ensure_network_allowed(self.chat_url)
            async with httpx.AsyncClient(trust_env=not settings.local_only_mode, timeout=max(self.timeout, 240.0)) as client:
                content = None
                for attempt in range(2):
                    response = await client.post(self.chat_url, headers=self.headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ProviderError("模型服务返回了无效响应")
                    if data.get("error") or data.get("errors"):
                        raise ProviderError(self._safe_error(data))
                    choices = data.get("choices")
                    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                    message = choice.get("message") or {}
                    content = message.get("content") if isinstance(message, dict) else None
                    truncated = choice.get("finish_reason") == "length"
                    if isinstance(content, str) and content.strip() and not truncated:
                        break
                    if attempt:
                        reason = "输出达到长度上限" if truncated else "返回了空内容或缺少页面响应"
                        raise ProviderError(f"模型{reason}，重试后仍未获得完整内容")
                    # One bounded retry; reasoning text never becomes slide copy.
                    if json_mode and "glm-" in model.lower():
                        payload["max_tokens"] = min(12000, max(4096, max_tokens * 2))
                        if urlparse(self.base_url).hostname == "api-inference.modelscope.cn":
                            payload["chat_template_kwargs"] = {"enable_thinking": False}
                        else:
                            payload["thinking"] = {"type": "disabled"}
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("模型返回了空内容")
            return content.strip()
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise ProviderError(detail) from exc

    async def vision_completion(
        self,
        model: str,
        prompt: str,
        images: list[bytes],
        max_tokens: int = 2400,
    ) -> str:
        content = [{"type": "text", "text": prompt}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64.b64encode(image).decode('ascii')}",
                    "detail": "high",
                },
            }
            for image in images
        )
        return await self.chat_completion(
            model,
            [{"role": "user", "content": content}],
            temperature=0.1,
            max_tokens=max_tokens,
            json_mode=True,
        )
