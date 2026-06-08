"""Helpers for resolving the AstrBot persona targeted by this plugin."""
import inspect
import time
from typing import Any, Dict, Optional


_WARNING_TTL_SECONDS = 300.0
_RECENT_WARNINGS: Dict[str, float] = {}


def _is_unset_mock(obj: Any, name: str) -> bool:
    return (
        obj is not None
        and obj.__class__.__module__ == "unittest.mock"
        and name not in getattr(obj, "__dict__", {})
    )


def _explicit_attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if obj.__class__.__module__ == "unittest.mock":
        children = getattr(obj, "_mock_children", {})
        if name in children:
            return children[name]
        if name in getattr(obj, "__dict__", {}):
            return getattr(obj, name)
        return None
    return getattr(obj, name, None)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def optional_object_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read optional attrs without auto-creating unittest.mock children."""
    if obj is None or _is_unset_mock(obj, name):
        return default
    return getattr(obj, name, default)


def get_configured_persona_id(config: Any) -> Optional[str]:
    """Return plugin-configured target persona ID, if explicitly configured."""
    value = optional_object_attr(config, "current_persona_name")
    if value is None:
        return None
    persona_id = str(value).strip()
    if not persona_id or persona_id == "[%None]" or persona_id.lower() == "default":
        return None
    return persona_id


def normalize_persona_data(persona: Any) -> Optional[Dict[str, Any]]:
    """Normalize AstrBot Persona objects and legacy Personality dicts."""
    if not persona:
        return None

    if isinstance(persona, dict):
        raw = dict(persona)
        persona_id = raw.get("persona_id") or raw.get("name")
        name = raw.get("name") or persona_id
        prompt = raw.get("prompt") or raw.get("system_prompt") or ""
        system_prompt = raw.get("system_prompt") or raw.get("prompt") or ""
        begin_dialogs = raw.get("begin_dialogs") or []
        tools = raw.get("tools")
    else:
        persona_id = getattr(persona, "persona_id", None)
        name = getattr(persona, "name", None) or persona_id
        prompt = getattr(persona, "prompt", None) or getattr(persona, "system_prompt", "") or ""
        system_prompt = getattr(persona, "system_prompt", None) or getattr(persona, "prompt", "") or ""
        begin_dialogs = getattr(persona, "begin_dialogs", None) or []
        tools = getattr(persona, "tools", None)
        raw = {}

    if persona_id is not None:
        persona_id = str(persona_id)
    if name is not None:
        name = str(name)

    normalized = {
        **raw,
        "persona_id": persona_id or name,
        "name": name or persona_id or "default",
        "prompt": prompt,
        "system_prompt": system_prompt,
        "begin_dialogs": begin_dialogs,
        "tools": tools,
    }
    return normalized


def get_persona_identifier(persona: Any, fallback: str = "default") -> str:
    normalized = normalize_persona_data(persona) or {}
    return str(normalized.get("persona_id") or normalized.get("name") or fallback)


def _warn(log: Any, message: str) -> None:
    if log and hasattr(log, "warning"):
        log.warning(message)


def _warn_once(log: Any, message: str, *, key: Optional[str] = None) -> None:
    if not log or not hasattr(log, "warning"):
        return
    cache_key = key or message
    now = time.monotonic()
    last = _RECENT_WARNINGS.get(cache_key)
    if last is not None and now - last < _WARNING_TTL_SECONDS:
        return
    _RECENT_WARNINGS[cache_key] = now
    log.warning(message)


async def _read_persona_by_id(
    persona_manager: Any,
    persona_id: str,
    log: Any = None,
) -> Optional[Dict[str, Any]]:
    get_persona = _explicit_attr(persona_manager, "get_persona")
    if not get_persona:
        return None
    try:
        persona = await _maybe_await(get_persona(persona_id))
    except Exception as exc:
        _warn_once(log, f"读取人格 {persona_id} 失败: {exc}", key=f"read:{persona_id}:{exc}")
        return None

    normalized = normalize_persona_data(persona)
    if normalized:
        returned_id = normalized.get("persona_id")
        if returned_id and str(returned_id) != persona_id:
            _warn_once(
                log,
                f"读取人格 {persona_id} 返回了 {returned_id}，按未命中处理",
                key=f"mismatch:{persona_id}:{returned_id}",
            )
            return None
        normalized["persona_id"] = returned_id or persona_id
        normalized.setdefault("name", normalized["persona_id"])
    return normalized


async def read_web_persona_by_id(persona_web_manager: Any, persona_id: str) -> Optional[Dict[str, Any]]:
    """Read a persona through PersonaWebManager's thread-safe WebUI surface."""
    if not persona_web_manager:
        return None
    get_persona_by_id = _explicit_attr(persona_web_manager, "get_persona_by_id")
    if get_persona_by_id:
        try:
            persona = await _maybe_await(get_persona_by_id(persona_id))
        except Exception:
            persona = None
        normalized = normalize_persona_data(persona)
        if normalized:
            return normalized
    get_all_personas = _explicit_attr(persona_web_manager, "get_all_personas_for_web")
    if not get_all_personas:
        return None

    personas = await _maybe_await(get_all_personas())
    for persona in personas or []:
        normalized = normalize_persona_data(persona)
        if normalized and normalized.get("persona_id") == persona_id:
            return normalized
    return None


async def resolve_target_persona_from_web(
    persona_web_manager: Any,
    config: Any = None,
    group_id: Optional[str] = None,
    *,
    log: Any = None,
) -> Optional[Dict[str, Any]]:
    """Resolve target persona through PersonaWebManager for WebUI threads."""
    if not persona_web_manager:
        return None

    configured_id = get_configured_persona_id(config)
    if configured_id:
        configured = await read_web_persona_by_id(persona_web_manager, configured_id)
        if configured:
            configured["selection_source"] = "plugin_config"
            return configured
        _warn_once(
            log,
            f"插件配置的人格 {configured_id} 不存在，将尝试 AstrBot 当前人格",
            key=f"web-config-missing:{configured_id}",
        )

    get_persona_for_group = _explicit_attr(persona_web_manager, "get_persona_for_group")
    get_all_personas = _explicit_attr(persona_web_manager, "get_all_personas_for_web")
    get_default_persona = _explicit_attr(persona_web_manager, "get_default_persona_for_web")

    if get_persona_for_group and group_id:
        current = await _maybe_await(get_persona_for_group(group_id))
        normalized = normalize_persona_data(current)
        if normalized and normalized.get("persona_id"):
            if get_all_personas or _explicit_attr(persona_web_manager, "get_persona_by_id"):
                existing = await read_web_persona_by_id(
                    persona_web_manager,
                    str(normalized["persona_id"]),
                )
                if existing:
                    existing["selection_source"] = "astrbot_default"
                    return existing
                _warn_once(
                    log,
                    f"AstrBot 当前人格 {normalized['persona_id']} 不存在于 PersonaManager",
                    key=f"web-current-missing:{normalized['persona_id']}",
                )
            else:
                normalized["selection_source"] = "astrbot_default"
                return normalized

    if get_default_persona:
        current = await _maybe_await(get_default_persona())
        normalized = normalize_persona_data(current)
        if normalized and normalized.get("persona_id"):
            if get_all_personas or _explicit_attr(persona_web_manager, "get_persona_by_id"):
                existing = await read_web_persona_by_id(
                    persona_web_manager,
                    str(normalized["persona_id"]),
                )
                if existing:
                    existing["selection_source"] = "astrbot_default"
                    return existing
                _warn_once(
                    log,
                    f"AstrBot 全局人格 {normalized['persona_id']} 不存在于 PersonaManager",
                    key=f"web-global-missing:{normalized['persona_id']}",
                )
            else:
                normalized["selection_source"] = "astrbot_default"
                return normalized

    if get_all_personas:
        personas = await _maybe_await(get_all_personas())
        normalized = [
            persona
            for persona in (normalize_persona_data(item) for item in (personas or []))
            if persona and persona.get("persona_id")
        ]
        if len(normalized) == 1:
            _warn_once(
                log,
                f"目标人格不可用，回退到唯一可用人格 {normalized[0]['persona_id']}",
                key=f"web-single-fallback:{normalized[0]['persona_id']}",
            )
            normalized[0]["selection_source"] = "single_existing"
            return normalized[0]

    return None


async def _read_single_existing_persona(
    persona_manager: Any,
    log: Any = None,
) -> Optional[Dict[str, Any]]:
    get_all_personas = _explicit_attr(persona_manager, "get_all_personas")
    if not persona_manager or not get_all_personas:
        return None
    try:
        personas = await _maybe_await(get_all_personas())
    except Exception as exc:
        _warn_once(log, f"读取人格列表失败: {exc}", key=f"list:{exc}")
        return None

    normalized = [
        persona
        for persona in (normalize_persona_data(item) for item in (personas or []))
        if persona and persona.get("persona_id")
    ]
    if len(normalized) == 1:
        _warn_once(
            log,
            f"目标人格不可用，回退到唯一可用人格 {normalized[0]['persona_id']}",
            key=f"single-fallback:{normalized[0]['persona_id']}",
        )
        return normalized[0]
    return None


async def resolve_target_persona(
    persona_manager: Any,
    config: Any = None,
    umo: Optional[str] = None,
    *,
    require_existing: bool = False,
    log: Any = None,
) -> Optional[Dict[str, Any]]:
    """Resolve the persona SelfLearning should read or mutate.

    Plugin config must take precedence over AstrBot's global default; otherwise
    learning updates can be written to a non-existent ``default`` persona.
    """
    if not persona_manager:
        return None

    configured_id = get_configured_persona_id(config)
    placeholder_persona: Optional[Dict[str, Any]] = None
    if configured_id:
        configured = await _read_persona_by_id(persona_manager, configured_id, log)
        if configured:
            configured["selection_source"] = "plugin_config"
            return configured
        _warn_once(
            log,
            f"插件配置的人格 {configured_id} 不存在，将尝试 AstrBot 当前人格",
            key=f"config-missing:{configured_id}",
        )

    get_default_persona = _explicit_attr(persona_manager, "get_default_persona_v3")
    if get_default_persona:
        try:
            default_persona = await _maybe_await(get_default_persona(umo))
        except Exception as exc:
            _warn_once(log, f"读取 AstrBot 当前人格失败: {exc}", key=f"current:{umo}:{exc}")
        else:
            normalized = normalize_persona_data(default_persona)
            if normalized:
                if not require_existing:
                    normalized["selection_source"] = "astrbot_default"
                    return normalized

                existing_id = normalized.get("persona_id")
                if existing_id and str(existing_id) != "default":
                    normalized["selection_source"] = "astrbot_default"
                    return normalized
                if existing_id:
                    _warn_once(
                        log,
                        "AstrBot 当前人格 default 可能是占位值，将尝试回退到可用人格",
                        key="current-placeholder-default",
                    )
                    placeholder_persona = normalized

        if umo != "default":
            try:
                default_persona = await _maybe_await(get_default_persona("default"))
            except Exception as exc:
                _warn_once(log, f"读取 AstrBot default 人格失败: {exc}", key=f"default:{exc}")
            else:
                normalized = normalize_persona_data(default_persona)
                if normalized:
                    if not require_existing:
                        normalized["selection_source"] = "astrbot_default"
                        return normalized

                    existing_id = normalized.get("persona_id")
                    if existing_id and str(existing_id) != "default":
                        normalized["selection_source"] = "astrbot_default"
                        return normalized
                    if existing_id:
                        _warn_once(
                            log,
                            "AstrBot default 人格可能是占位值，将尝试回退到可用人格",
                            key="current-placeholder-default",
                        )
                        placeholder_persona = placeholder_persona or normalized

    if require_existing:
        single_persona = await _read_single_existing_persona(persona_manager, log)
        if single_persona:
            if placeholder_persona and str(single_persona.get("persona_id") or "").lower() == "default":
                placeholder_persona["selection_source"] = "astrbot_default_placeholder"
                return placeholder_persona
            single_persona["selection_source"] = "single_existing"
            return single_persona
        if placeholder_persona:
            placeholder_persona["selection_source"] = "astrbot_default_placeholder"
            return placeholder_persona

    return None
