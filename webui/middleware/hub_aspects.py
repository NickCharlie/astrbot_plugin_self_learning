"""AOP-style wrappers for the stable Self Learning Hub API."""

from __future__ import annotations

import time
import secrets
from functools import wraps
from typing import Any, Callable

from quart import jsonify, request

try:
    from ...utils.logging_utils import get_astrbot_logger
except ImportError:
    from utils.logging_utils import get_astrbot_logger

from ..dependencies import get_container

logger = get_astrbot_logger("self_learning.webui.hub")


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


def require_hub_api_key(handler: Callable):
    """Require API key auth when API_Settings.enable_api_auth is enabled."""

    @wraps(handler)
    async def wrapper(*args, **kwargs):
        config = getattr(get_container(), "plugin_config", None)
        enabled = bool(getattr(config, "enable_api_auth", False))
        expected = str(getattr(config, "api_key", "") or "")
        if not enabled:
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
