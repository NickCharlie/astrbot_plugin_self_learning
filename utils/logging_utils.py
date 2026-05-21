"""Logging helpers for the plugin."""

from __future__ import annotations

import logging
from typing import Optional

from astrbot.api import logger as astrbot_logger


_PLUGIN_LOGGER_NAME = "self_learning"
_PLUGIN_TAG = "[Plug]"
_FILTER_FLAG = "_self_learning_log_record_defaults"

_LOG_LEVELS = {
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

_LEVEL_ALIASES = {
    "warn": "warning",
    "err": "error",
    "fatal": "error",
    "critical": "error",
}


class _AstrBotRecordDefaults(logging.Filter):
    """Ensure plugin child loggers satisfy AstrBot's formatter fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "plugin_tag"):
            record.plugin_tag = _PLUGIN_TAG
        if not hasattr(record, "short_levelname"):
            record.short_levelname = record.levelname[:4].upper()
        if not hasattr(record, "astrbot_version_tag"):
            record.astrbot_version_tag = ""
        if not hasattr(record, "source_file"):
            record.source_file = record.name
        if not hasattr(record, "source_line"):
            record.source_line = record.lineno
        if not hasattr(record, "is_trace"):
            record.is_trace = False
        if not hasattr(record, "ansi_prefix"):
            record.ansi_prefix = ""
        if not hasattr(record, "ansi_reset"):
            record.ansi_reset = ""
        return True


def _ensure_record_defaults(logger: logging.Logger) -> logging.Logger:
    has_filter = any(getattr(existing, _FILTER_FLAG, False) for existing in logger.filters)
    if not has_filter:
        record_filter = _AstrBotRecordDefaults()
        setattr(record_filter, _FILTER_FLAG, True)
        logger.addFilter(record_filter)
    return logger


def normalize_log_level(
    level_name: Optional[str],
    *,
    debug_mode: bool = False,
    fallback: str = "info",
) -> str:
    """Return a supported lowercase log level name."""
    candidate = str(level_name or "").strip().lower()
    candidate = _LEVEL_ALIASES.get(candidate, candidate)

    if not candidate:
        return "debug" if debug_mode else fallback

    if candidate in _LOG_LEVELS:
        return candidate

    return "debug" if debug_mode else fallback


def resolve_log_level(
    level_name: Optional[str],
    *,
    debug_mode: bool = False,
    fallback: str = "info",
) -> int:
    """Return the numeric logging level."""
    normalized = normalize_log_level(
        level_name,
        debug_mode=debug_mode,
        fallback=fallback,
    )
    return _LOG_LEVELS[normalized]


def apply_astrbot_log_level(
    level_name: Optional[str],
    *,
    debug_mode: bool = False,
    fallback: str = "info",
) -> str:
    """Apply the selected level to this plugin's AstrBot logger tree."""
    normalized = normalize_log_level(
        level_name,
        debug_mode=debug_mode,
        fallback=fallback,
    )
    astrbot_logger.getChild(_PLUGIN_LOGGER_NAME).setLevel(_LOG_LEVELS[normalized])
    return normalized


def get_astrbot_logger(name: Optional[str] = None) -> logging.Logger:
    """Create a child logger under the AstrBot root logger."""
    if not name:
        return _ensure_record_defaults(astrbot_logger.getChild(_PLUGIN_LOGGER_NAME))

    logger_name = name.strip(".")
    if logger_name == _PLUGIN_LOGGER_NAME or logger_name.startswith(f"{_PLUGIN_LOGGER_NAME}."):
        return _ensure_record_defaults(astrbot_logger.getChild(logger_name))
    return _ensure_record_defaults(astrbot_logger.getChild(f"{_PLUGIN_LOGGER_NAME}.{logger_name}"))


__all__ = [
    "apply_astrbot_log_level",
    "get_astrbot_logger",
    "normalize_log_level",
    "resolve_log_level",
]
