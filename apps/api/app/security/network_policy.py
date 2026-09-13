import ipaddress
from urllib.parse import urlsplit

from app.config import settings


def ensure_network_allowed(url: str):
    if not settings.local_only_mode:
        return
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("完全本地模式不支持此地址")
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("完全本地模式已阻止外部连接，请配置 127.0.0.1 或 localhost 上的模型服务")
