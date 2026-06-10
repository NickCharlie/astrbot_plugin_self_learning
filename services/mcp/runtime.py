"""Runtime helpers for the self-learning MCP server.

The MCP server is designed to run outside AstrBot while reusing the plugin's
database and service layer.  Some existing modules import ``astrbot.api`` for
logging, so this module installs a minimal compatibility shim only when the
real AstrBot package is unavailable.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import types
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


def ensure_astrbot_compat() -> None:
    """Install a tiny ``astrbot.api.logger`` shim when AstrBot is absent."""
    existing_api = sys.modules.get("astrbot.api")
    existing_logger = getattr(existing_api, "logger", None)
    if isinstance(existing_logger, logging.Logger):
        _configure_logger_for_mcp(existing_logger)
        return

    try:
        if importlib.util.find_spec("astrbot.api") is not None:
            import astrbot.api as astrbot_api

            _configure_logger_for_mcp(astrbot_api.logger)
            return
    except (ImportError, ValueError):
        pass

    root = logging.getLogger("astrbot")
    _configure_logger_for_mcp(root)

    astrbot_module = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    api_module = sys.modules.setdefault("astrbot.api", types.ModuleType("astrbot.api"))
    setattr(api_module, "logger", root)
    setattr(astrbot_module, "api", api_module)


def _configure_logger_for_mcp(logger: logging.Logger) -> logging.Logger:
    """Route AstrBot logs to stderr so stdio transport keeps stdout clean."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


ensure_astrbot_compat()

try:
    from ...config import PluginConfig
    from ...services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
    from ...statics.messages import FileNames
except ImportError:
    from config import PluginConfig
    from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
    from statics.messages import FileNames


@dataclass(slots=True)
class McpRuntimeSettings:
    """Runtime settings for the self-learning MCP server."""

    data_dir: Optional[str] = None
    config_file: Optional[str] = None
    db_type: Optional[str] = None
    messages_db_path: Optional[str] = None


SENSITIVE_CONFIG_KEYS = {
    "api_key",
    "mysql_password",
    "postgresql_password",
    "password",
    "secret",
    "token",
}


def clamp(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)


def ok(data: Any = None, **extra: Any) -> str:
    payload = {"success": True, "data": data}
    payload.update(extra)
    return json_dumps(payload)


def fail(message: str, *, error_type: str = "runtime_error", **extra: Any) -> str:
    payload = {
        "success": False,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    payload.update(extra)
    return json_dumps(payload)


def paginate(items: list[Any], *, total: Optional[int], limit: int, offset: int) -> dict[str, Any]:
    count = len(items)
    resolved_total = total if total is not None else offset + count
    next_offset = offset + count if resolved_total > offset + count else None
    return {
        "items": items,
        "count": count,
        "total": resolved_total,
        "limit": limit,
        "offset": offset,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
    }


def mask_config(config: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in config.items():
        lowered = key.lower()
        if any(marker in lowered for marker in SENSITIVE_CONFIG_KEYS):
            masked[key] = "***" if value else value
        elif isinstance(value, dict):
            masked[key] = mask_config(value)
        else:
            masked[key] = value
    return masked


def normalize_action(action: str) -> str:
    normalized = str(action or "").strip().lower()
    if normalized in {"approve", "approved", "accept", "confirm"}:
        return "approved"
    if normalized in {"reject", "rejected", "deny"}:
        return "rejected"
    raise ValueError("action must be approve or reject")


def normalize_status(status: Optional[str]) -> str:
    normalized = str(status or "pending").strip().lower()
    aliases = {
        "approve": "approved",
        "accept": "approved",
        "reject": "rejected",
        "deny": "rejected",
    }
    return aliases.get(normalized, normalized)


class SelfLearningMcpRuntime:
    """Lazy database runtime shared by MCP tools."""

    def __init__(self, settings: McpRuntimeSettings | None = None) -> None:
        self.settings = settings or McpRuntimeSettings()
        self.config = self._load_config()
        self.database_manager: SQLAlchemyDatabaseManager | None = None
        self.database_start_error: str | None = None
        self._db_lock = asyncio.Lock()

    async def get_db(self) -> SQLAlchemyDatabaseManager:
        async with self._db_lock:
            if self.database_manager and self.database_manager.is_ready:
                return self.database_manager

            manager = SQLAlchemyDatabaseManager(self.config)
            started = await manager.start()
            if not started:
                self.database_start_error = "database manager returned False from start()"
                raise RuntimeError(
                    "Database startup failed. Check database settings or set "
                    "SELF_LEARNING_DB_TYPE=sqlite for a local SQLite database."
                )

            self.database_manager = manager
            self.database_start_error = None
            return manager

    async def call(
        self,
        operation: Callable[[SQLAlchemyDatabaseManager], Awaitable[Any]],
        *,
        transform: Callable[[Any], Any] | None = None,
    ) -> str:
        try:
            db = await self.get_db()
            result = await operation(db)
            if transform is not None:
                result = transform(result)
            return ok(result)
        except Exception as exc:
            return fail(
                str(exc),
                error_type=type(exc).__name__,
                runtime_status=self.status(include_config=False),
            )

    async def close(self) -> None:
        if self.database_manager:
            await self.database_manager.stop()
            self.database_manager = None

    def status(self, *, include_config: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "database_ready": bool(
                self.database_manager and self.database_manager.is_ready
            ),
            "database_start_error": self.database_start_error,
            "data_dir": self.config.data_dir,
            "db_type": self.config.db_type,
            "messages_db_path": self.config.messages_db_path,
        }
        if include_config:
            data["config"] = mask_config(self.config.to_dict())
        return data

    def _load_config(self) -> PluginConfig:
        data_dir = self._resolve_path(
            self.settings.data_dir
            or os.getenv("SELF_LEARNING_DATA_DIR")
            or os.getenv("ASTRBOT_SELF_LEARNING_DATA_DIR")
        )
        config_file = self._resolve_path(
            self.settings.config_file
            or os.getenv("SELF_LEARNING_CONFIG_FILE")
            or os.getenv("ASTRBOT_SELF_LEARNING_CONFIG_FILE")
        )

        if not data_dir:
            data_dir = self._resolve_path(os.getenv("SELF_LEARNING_PLUGIN_DATA_DIR"))

        if data_dir and not config_file:
            config_file = str(Path(data_dir) / FileNames.CONFIG_FILE)

        config = PluginConfig.create_from_runtime_sources(
            {},
            data_dir=data_dir,
            config_file=config_file,
        )

        db_type = self.settings.db_type or os.getenv("SELF_LEARNING_DB_TYPE")
        if db_type:
            config.db_type = db_type

        messages_db_path = self._resolve_path(
            self.settings.messages_db_path
            or os.getenv("SELF_LEARNING_MESSAGES_DB_PATH")
        )
        if messages_db_path:
            config.messages_db_path = messages_db_path

        if not config.messages_db_path:
            config.messages_db_path = str(Path(config.data_dir) / FileNames.MESSAGES_DB_FILE)

        return config

    @staticmethod
    def _resolve_path(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return str(Path(os.path.expandvars(os.path.expanduser(value))).resolve())


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)
