"""Framework API compatibility helpers."""

import inspect
import re
from typing import Any, Optional


async def get_using_provider_compat(context: Any):
    """Resolve the current chat provider across AstrBot versions.

    AstrBot v4.27 deprecates the sync ``Context.get_using_provider()`` in
    favour of ``get_using_provider_async()`` (the sync version emits a
    runtime DeprecationWarning). Older versions only ship the sync one, so
    prefer the async accessor when it is a real coroutine function and fall
    back otherwise.

    Args:
        context: The plugin ``Context`` (or any compatible object).

    Returns:
        The active chat provider, or ``None`` when unavailable.
    """
    async_getter = getattr(context, "get_using_provider_async", None)
    if inspect.iscoroutinefunction(async_getter):
        return await async_getter()
    sync_getter = getattr(context, "get_using_provider", None)
    if sync_getter is None:
        return None
    return sync_getter()


_PLUGIN_VIEW_MIN_VERSION = (4, 29, 0)


def _parse_version_tuple(version: Any) -> Optional[tuple[int, ...]]:
    """Parse a leading dotted version string into an int tuple.

    Each chunk contributes its leading digits, so prerelease suffixes attach
    to their own segment (``4.29.0rc1`` → ``(4, 29, 0)``). Returns ``None``
    when nothing numeric can be parsed, so callers can fall back to the most
    conservative behaviour.
    """
    parts: list[int] = []
    for chunk in re.split(r"[.\-+ _]", str(version or "")):
        match = re.match(r"\d+", chunk)
        if match:
            parts.append(int(match.group()))
        elif parts:
            break
    return tuple(parts) or None


def plugin_page_hash_prefix() -> str:
    """Hash-router prefix of the AstrBot plugin view (formerly page) entry.

    AstrBot v4.29 renamed plugin Pages to Views and moved the dashboard
    route to ``/plugin-view/<plugin>/<page>``, keeping ``/plugin-page/...``
    only as a legacy alias (AstrBot commits 4b049d1e5, 8831d9502). Emit the
    new prefix on v4.29+ and keep the legacy one elsewhere — it resolves on
    every version this plugin supports.
    """
    try:
        from astrbot import __version__
    except Exception:
        return "#/plugin-page"
    parsed = _parse_version_tuple(__version__)
    if parsed and parsed >= _PLUGIN_VIEW_MIN_VERSION:
        return "#/plugin-view"
    return "#/plugin-page"


def plugin_page_hash_url(plugin_name: str, page_name: str) -> str:
    """Full in-dashboard hash URL for a plugin view page."""
    from urllib.parse import quote

    return (
        f"{plugin_page_hash_prefix()}"
        f"/{quote(str(plugin_name), safe='')}/{quote(str(page_name), safe='')}"
    )


def plugin_view_dir_names() -> tuple[str, ...]:
    """Plugin view directory conventions supported by the running AstrBot.

    AstrBot v4.29's plugin page service discovers ``views/`` first and keeps
    ``pages/`` for compatibility (``PLUGIN_PAGE_ROOT_DIR_NAMES``); older
    versions only discover ``pages/``, so advertising view-directory pages
    there would produce dead official-page links.
    """
    try:
        from astrbot import __version__
    except Exception:
        return ("pages",)
    parsed = _parse_version_tuple(__version__)
    if parsed and parsed >= _PLUGIN_VIEW_MIN_VERSION:
        return ("views", "pages")
    return ("pages",)
