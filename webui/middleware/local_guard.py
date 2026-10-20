"""网络层访问守卫：免密模式限本机 + 同源校验（防跨站读取/DNS 重绑定）。

背景（4.3.x 安全加固）：

- WebUI 默认 ``enable_webui_password=False``（免密）且历史默认 ``0.0.0.0``
  绑定，整套管理 API（聊天记录、人格改写、数据清空、配置读写等约 140 个
  端点）会对局域网无门槛开放。
- 免密模式下 ``CORS allow_origins=["*"]`` 允许任意网页用受害者浏览器读取
  本机 API 响应；DNS 重绑定可绕过"访问的是 127.0.0.1"的直觉。

守卫规则（按请求在最外层执行）：

1. 免密模式：客户端 socket 地址必须为 loopback，且 ``Host`` 头必须指向
   本机（拦截局域网直连与 DNS 重绑定）。开启密码后放开（由登录会话保护）。
2. 全模式：携带 ``Origin`` 头的请求必须与 ``Host`` 同源（浏览器跨站请求
   必带 Origin；服务器间调用不带），拦截跨站读取与 CSRF。
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse


def _is_loopback_ip(host: str) -> bool:
    normalized = str(host or "").strip().strip("[]").lower()
    if not normalized:
        return False
    if normalized == "localhost":
        return True
    # 只接受 IP 字面量：形如 127.evil.com 的攻击者域名不能靠字符串前缀混过校验
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback or addr.is_unspecified


def _header_value(headers: list, name: bytes) -> str:
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1", errors="ignore")
    return ""


def _origin_matches_host(origin: str, host_header: str) -> bool:
    """Origin 与 Host 头是否同源（host 不分大小写，端口按显式值/协议默认值比较）。"""
    try:
        origin_parts = urlsplit(origin)
        host_parts = urlsplit(f"//{host_header}" if "//" not in host_header else host_header)
    except ValueError:
        return False
    origin_host = (origin_parts.hostname or "").lower()
    request_host = (host_parts.hostname or "").lower()
    if not origin_host or not request_host:
        return False
    if origin_host != request_host and not (
        _is_loopback_ip(origin_host) and _is_loopback_ip(request_host)
    ):
        # 仅 127.0.0.1 ↔ localhost 这类本机别名视为同源
        return False
    origin_port = origin_parts.port
    request_port = host_parts.port
    if origin_port is not None and request_port is not None:
        return origin_port == request_port
    if origin_port is None and request_port is None:
        return True
    # 一方省缺端口时按协议默认端口补齐（Host 无 scheme，随 Origin 推导）
    default_port = 443 if origin_parts.scheme == "https" else 80
    return (origin_port if origin_port is not None else default_port) == (
        request_port if request_port is not None else default_port
    )


def _password_enabled() -> bool:
    from ..dependencies import get_container

    try:
        config = getattr(get_container(), "plugin_config", None)
    except Exception:
        return False
    return bool(getattr(config, "enable_webui_password", False))


def _reject_message(scope: dict) -> str | None:
    headers = scope.get("headers") or []
    client = scope.get("client")
    client_host = client[0] if isinstance(client, (tuple, list)) and client else ""

    origin = _header_value(headers, b"origin")
    host_header = _header_value(headers, b"host")

    if not _password_enabled():
        if not _is_loopback_ip(client_host):
            return (
                "WebUI 免密模式仅允许本机访问。局域网访问请开启"
                " enable_webui_password 并设置登录密码。"
            )
        host_name = (urlsplit(f"//{host_header}").hostname or "").lower() if host_header else ""
        if host_name and not _is_loopback_ip(host_name):
            return (
                f"Host 头（{host_header}）非本机地址，已按 DNS 重绑定风险拦截。"
                "如经反向代理访问，请先开启 WebUI 登录密码。"
            )
    if origin and not _origin_matches_host(origin, host_header):
        return "跨站请求已被拒绝（Origin 与面板地址不同源）。"
    return None


class LocalAccessGuardMiddleware:
    """纯 ASGI 中间件：路由之前做网络层访问校验。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        message = _reject_message(scope)
        if message is None:
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            {"success": False, "message": message},
            status_code=403,
        )
        await response(scope, receive, send)
