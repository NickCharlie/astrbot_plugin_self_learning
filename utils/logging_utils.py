"""Logging helpers for the plugin."""

from __future__ import annotations

import logging
from typing import Optional

from astrbot.api import logger as astrbot_logger


_PLUGIN_LOGGER_NAME = "self_learning"

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
        return astrbot_logger.getChild(_PLUGIN_LOGGER_NAME)

    logger_name = name.strip(".")
    if logger_name == _PLUGIN_LOGGER_NAME or logger_name.startswith(f"{_PLUGIN_LOGGER_NAME}."):
        return astrbot_logger.getChild(logger_name)
    return astrbot_logger.getChild(f"{_PLUGIN_LOGGER_NAME}.{logger_name}")


__all__ = [
    "apply_astrbot_log_level",
    "get_astrbot_logger",
    "normalize_log_level",
    "resolve_log_level",
]
