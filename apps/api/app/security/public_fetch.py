"""Bounded HTTP downloads for user supplied public URLs."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class PublicFetchError(ValueError):
    pass


class _PinnedDNSBackend(httpcore.AsyncNetworkBackend):
    def __init__(self):
        from httpcore._backends.auto import AutoBackend

        self._backend = AutoBackend()
        self._pinned: dict[tuple[str, int], str] = {}

    def pin(self, hostname: str, port: int, address: str) -> None:
        self._pinned[(hostname.rstrip(".").lower(), port)] = address

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        address = self._pinned.get((host.rstrip(".").lower(), port), host)
        return await self._backend.connect_tcp(
            address, port, timeout=timeout, local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return await self._backend.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds):
        return await self._backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False, retries=0)
        self.pinned_backend = _PinnedDNSBackend()
        pool = getattr(self, "_pool", None)
        if pool is None or not hasattr(pool, "_network_backend"):
            raise RuntimeError("当前 HTTPX/httpcore 版本不支持安全固定网页解析地址")
        pool._network_backend = self.pinned_backend


async def _validated_target(url: str) -> tuple[str, int, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise PublicFetchError("只允许不带凭据的 HTTP 或 HTTPS 公网网址")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        records = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, port, 0, socket.SOCK_STREAM
        )
        addresses = [ipaddress.ip_address(record[4][0].split("%", 1)[0]) for record in records]
    except (OSError, ValueError) as exc:
        raise PublicFetchError("无法安全解析网址") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise PublicFetchError("网址解析到了非公网地址")
    return parsed.hostname, port, str(addresses[0])


async def fetch_public_bytes(
    url: str, *, max_bytes: int, timeout: float = 45, user_agent: str = "YingZhang/0.2"
) -> tuple[bytes, str, str]:
    """Fetch a public URL, validating and pinning every redirect, with a hard body cap."""
    transport = _PinnedHTTPTransport()
    chunks = bytearray()
    current_url = url
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=False, transport=transport
        ) as client:
            for redirect_count in range(MAX_REDIRECTS + 1):
                hostname, port, address = await _validated_target(current_url)
                transport.pinned_backend.pin(hostname, port, address)
                async with client.stream(
                    "GET", current_url, headers={"User-Agent": user_agent}
                ) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location or redirect_count == MAX_REDIRECTS:
                            raise PublicFetchError("网址跳转过多或缺少跳转目标")
                        current_url = urljoin(str(response.url), location)
                        continue
                    response.raise_for_status()
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise PublicFetchError(f"下载内容超过 {max_bytes} 字节上限")
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            raise PublicFetchError(f"下载内容超过 {max_bytes} 字节上限")
                    return bytes(chunks), response.headers.get("content-type", "application/octet-stream"), str(response.url)
            raise PublicFetchError("网址跳转过多")
    except PublicFetchError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise PublicFetchError("无法读取该网址，请检查地址和服务状态") from exc
