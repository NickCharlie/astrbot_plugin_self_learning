"""AOP-style wrappers for the stable Self Learning Hub API."""

from __future__ import annotations

import time
import secrets
from functools import wraps
from typing import Any, Callable
from urllib.parse import urlsplit

from astrbot.api import logger
from ..compat import jsonify, request

from ..dependencies import get_container


class HubApiError(Exception):
    """Expected Hub API failure with an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def hub_success(data: Any = None, *, message: str = "ok", meta: dict[str, Any] | None = None):
    """Return the Hub API's stable success envelope."""
    payload = {
        "success": True,
        "message": message,
        "data": data if data is not None else {},
    }
    if meta:
        payload["meta"] = meta
    return jsonify(payload), 200


def hub_error(
    message: str,
    status_code: int = 400,
    *,
    code: str = "bad_request",
    data: Any = None,
):
    """Return the Hub API's stable error envelope."""
    payload = {
        "success": False,
        "message": message,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code


def _request_client_is_loopback() -> bool:
    """Hub 调用方（伴随插件）应与本插件同机；跨机调用必须启用 API key。"""
    client = None
    try:
        # 兼容层的 request 代理暴露 starlette 的 .client（Address 对象）
        client = getattr(request, "client", None)
    except RuntimeError:
        return False
    if client is None:
        scope = getattr(request, "scope", None) or {}
        client = scope.get("client")
    if hasattr(client, "host"):
        host = client.host
    elif isinstance(client, (tuple, list)) and client:
        host = client[0]
    else:
        return False
    normalized = str(host or "").strip().strip("[]").lower()
    if normalized.startswith("::ffff:"):
        normalized = normalized[len("::ffff:"):]
    return (
        normalized in {"localhost", "::1", "0.0.0.0"}
        or normalized.startswith("127.")
    )


def _request_host_is_loopback() -> bool:
    """Host 头是否指向本机：同机反代转发远程请求时 socket 是 loopback，
    但 Host 是外部域名，据此识别并拒绝（远程调用请启用 API key）。"""
    try:
        host = request.headers.get("Host", "") or ""
    except RuntimeError:
        return False
    if not host:
        return True
    from ..middleware.local_guard import _is_loopback_ip

    try:
        hostname = urlsplit(f"//{host}").hostname or ""
    except ValueError:
        return False
    return _is_loopback_ip(hostname)


def require_hub_api_key(handler: Callable):
    """Require API key auth when API_Settings.enable_api_auth is enabled."""

    @wraps(handler)
    async def wrapper(*args, **kwargs):
        config = getattr(get_container(), "plugin_config", None)
        enabled = bool(getattr(config, "enable_api_auth", False))
        expected = str(getattr(config, "api_key", "") or "")
        if not enabled:
            # 未启用 API key 时降级为"仅本机可调用"：Hub API 可写记忆、审批
            # 人格与注入消息，不能对局域网/反代转发无门槛开放。
            if not _request_client_is_loopback() or not _request_host_is_loopback():
                return hub_error(
                    "Hub API 鉴权未启用（enable_api_auth=false），仅允许本机调用；"
                    "跨机调用请配置 api_key 并启用 enable_api_auth",
                    403,
                    code="loopback_only",
                )
            return await handler(*args, **kwargs)
        if not expected:
            return hub_error(
                "Hub API auth is enabled but api_key is empty",
                503,
                code="api_key_not_configured",
            )

        supplied = request.headers.get("X-Self-Learning-Key", "")
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            supplied = auth_header.split(" ", 1)[1].strip()

        if not secrets.compare_digest(str(supplied), expected):
            return hub_error("Unauthorized", 401, code="unauthorized")
        return await handler(*args, **kwargs)

    return wrapper


def hub_endpoint(handler: Callable):
    """Apply consistent timing, logging, and error mapping to Hub routes."""

    @wraps(handler)
    async def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return await handler(*args, **kwargs)
        except HubApiError as exc:
            return hub_error(exc.message, exc.status_code, code=exc.code)
        except Exception as exc:
            logger.error(f"Hub API route failed: {exc}", exc_info=True)
            return hub_error("Internal Hub API error", 500, code="internal_error")
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.debug(
                f"[Hub API] {request.method} {request.path} completed in {elapsed_ms:.1f}ms"
            )

    return wrapper


def hub_route(handler: Callable):
    """Decorator stack for public Hub API endpoints."""
    return require_hub_api_key(hub_endpoint(handler))
