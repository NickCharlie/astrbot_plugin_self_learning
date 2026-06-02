"""Learning-sample filters for command, framework, and runtime log messages."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


COMMAND_PREFIXES = ("/", "!", "#", ".")
BARE_COMMANDS = {
    "help",
    "new",
    "provider",
    "reset",
    "history",
    "persona",
    "plugin",
    "model",
    "tools",
}

SYSTEM_RESPONSE_PATTERNS = (
    re.compile(r"^AstrBot\s+v?\d", re.IGNORECASE),
    re.compile(r"^/[\w-]+\s+-\s+", re.MULTILINE),
    re.compile(r"^(Traceback|Exception|Error|TimeoutError):", re.IGNORECASE),
    re.compile(
        r"(调用超时|请求超时|发生错误|模型调用失败|Provider\s+.*未配置|timeout)",
        re.IGNORECASE,
    ),
)

NON_CHAT_EVENT_VALUES = {
    "notice",
    "request",
    "meta_event",
    "system",
    "system_event",
    "log",
    "logger",
    "runtime_log",
    "plugin_log",
    "plugin_output",
    "console",
    "lifecycle",
    "heartbeat",
    "status",
}
CHAT_EVENT_VALUES = {
    "message",
    "group",
    "friend",
    "private",
    "group_message",
    "friend_message",
    "private_message",
    "normal",
}
SOURCE_LOG_VALUES = {
    "log",
    "logger",
    "runtime_log",
    "plugin_log",
    "plugin_output",
    "console",
    "system",
}
METADATA_FIELD_NAMES = (
    "source",
    "message_type",
    "event_type",
    "post_type",
    "sub_type",
    "notice_type",
    "plugin_name",
)

LOG_LEVEL_PATTERN = r"(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)"
PLUGIN_RUNTIME_CONTEXT_PATTERN = (
    r"(?:LivingMemory|astrbot_plugin_livingmemory|MemoryEngine|"
    r"ConversationManager|FaissVecDB|FAISS|BM25|WebUI|"
    r"EventHandler|ConversationStore|MemoryProcessor)"
)
PLUGIN_RUNTIME_ACTION_PATTERN = (
    r"(?:初始化|启动|停止|关闭|退出|失败|异常|成功|超时|耗时|"
    r"重建|索引|检索|同步|清空|清理|连接|写入|删除|更新|回滚)"
)
CONVERSATIONAL_CUE_PATTERN = re.compile(
    r"(?:\?|？|吗|呢|为什么|怎么|如何|什么时候|能不能|是不是|可以|有人|我|你)"
)
PLUGIN_LOG_PATTERNS = (
    re.compile(
        rf"^\s*(?:\[[^\]]+\]\s*){{0,3}}\[[^\]]*(?:{LOG_LEVEL_PATTERN})[^\]]*\].*"
        rf"(?:{PLUGIN_RUNTIME_CONTEXT_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*(?:\d{{4}}-\d{{2}}-\d{{2}}[ T]\d{{2}}:\d{{2}}:\d{{2}}"
        rf"(?:[.,]\d+)?|\d{{2}}:\d{{2}}:\d{{2}}(?:[.,]\d+)?)\s+"
        rf"{LOG_LEVEL_PATTERN}\b.*(?:{PLUGIN_RUNTIME_CONTEXT_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*(?:\[[^\]]*(?:{PLUGIN_RUNTIME_CONTEXT_PATTERN})[^\]]*\]\s*)?"
        rf"(?:{PLUGIN_RUNTIME_CONTEXT_PATTERN})\b.*"
        rf"(?:{PLUGIN_RUNTIME_ACTION_PATTERN})",
        re.IGNORECASE,
    ),
)


def _normalize_text(message_text: Any) -> str:
    return "" if message_text is None else str(message_text).strip()


def _metadata_values(value: Any) -> List[str]:
    if value is None:
        return []

    values: List[str] = []
    for attr in ("value", "name"):
        attr_value = getattr(value, attr, None)
        if attr_value is not None and attr_value is not value:
            values.append(str(attr_value))
    values.append(str(value))
    return [item.strip().lower() for item in values if str(item).strip()]


def _normalize_metadata_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _is_chat_event_value(value: Any) -> bool:
    for raw in _metadata_values(value):
        token = _normalize_metadata_token(raw)
        if token in CHAT_EVENT_VALUES:
            return True
        if any(chat_token in token for chat_token in (
            "group_message",
            "friend_message",
            "private_message",
        )):
            return True
    return False


def _is_non_chat_event_value(value: Any) -> bool:
    if value is None or _is_chat_event_value(value):
        return False

    for raw in _metadata_values(value):
        token = _normalize_metadata_token(raw)
        if token in NON_CHAT_EVENT_VALUES:
            return True
        token_parts = {part for part in token.split("_") if part}
        if token_parts & NON_CHAT_EVENT_VALUES:
            return True
    return False


def _is_log_source(value: Any) -> bool:
    if value is None:
        return False

    for raw in _metadata_values(value):
        token = _normalize_metadata_token(raw)
        if token in SOURCE_LOG_VALUES:
            return True
        token_parts = {part for part in token.split("_") if part}
        if token_parts & SOURCE_LOG_VALUES:
            return True
    return False


def has_system_event_metadata(
    *,
    source: Any = None,
    message_type: Any = None,
    event_type: Any = None,
    post_type: Any = None,
    sub_type: Any = None,
    notice_type: Any = None,
    plugin_name: Any = None,
    metadata: Any = None,
) -> bool:
    """Return true when structured event fields identify non-chat output."""
    if any(
        _is_non_chat_event_value(value)
        for value in (message_type, event_type, post_type, sub_type, notice_type)
    ):
        return True

    if _is_log_source(source):
        return True

    if _is_log_source(plugin_name) and (
        event_type is not None or post_type is not None or message_type is not None
    ):
        return True

    if isinstance(metadata, dict):
        return has_system_event_metadata(
            source=metadata.get("source", source),
            message_type=metadata.get("message_type", message_type),
            event_type=metadata.get("event_type", event_type),
            post_type=metadata.get("post_type", post_type),
            sub_type=metadata.get("sub_type", sub_type),
            notice_type=metadata.get("notice_type", notice_type),
            plugin_name=metadata.get("plugin_name", plugin_name),
        )

    return False


def extract_learning_event_metadata(event: Any) -> Dict[str, Any]:
    """Extract optional event metadata used by sample filtering."""
    if event is None:
        return {}

    metadata: Dict[str, Any] = {}
    method_map = {
        "message_type": "get_message_type",
        "event_type": "get_event_type",
        "source": "get_source",
    }
    for key, method_name in method_map.items():
        method = getattr(event, method_name, None)
        if not callable(method):
            continue
        try:
            value = method()
        except Exception:
            continue
        if value is not None:
            metadata[key] = value

    for key in METADATA_FIELD_NAMES:
        if key in metadata:
            continue
        value = getattr(event, key, None)
        if value is not None:
            metadata[key] = value

    raw_event = getattr(event, "raw_event", None) or getattr(event, "raw", None)
    if isinstance(raw_event, dict):
        metadata["metadata"] = raw_event
        for key in METADATA_FIELD_NAMES:
            if key not in metadata and raw_event.get(key) is not None:
                metadata[key] = raw_event.get(key)

    return metadata


def is_command_message(message_text: Any) -> bool:
    """Return true for explicit AstrBot command inputs."""
    text = _normalize_text(message_text)
    if not text:
        return False

    first_token = text.split(maxsplit=1)[0].strip()
    has_prefix = first_token[:1] in COMMAND_PREFIXES and len(first_token) > 1
    normalized = first_token[1:].lower() if has_prefix else first_token.lower()

    if has_prefix:
        return normalized in BARE_COMMANDS
    return text.lower() in BARE_COMMANDS


def is_system_response(message_text: Any) -> bool:
    """Return true for framework help/error output that should not be learned."""
    text = _normalize_text(message_text)
    if not text:
        return False

    if any(pattern.search(text) for pattern in SYSTEM_RESPONSE_PATTERNS):
        return True

    help_lines = sum(
        1
        for line in text.splitlines()
        if re.match(r"^/[\w-]+\s+-\s+", line.strip())
    )
    return help_lines >= 2


def is_plugin_log_message(message_text: Any) -> bool:
    """Return true for plugin/runtime log lines that are not user chat."""
    text = _normalize_text(message_text)
    if not text:
        return False

    has_log_shape = bool(
        re.match(rf"^\s*(?:\[.*{LOG_LEVEL_PATTERN}.*\]|{LOG_LEVEL_PATTERN}\b)", text, re.IGNORECASE)
        or re.match(
            r"^\s*(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2})",
            text,
        )
    )
    for idx, pattern in enumerate(PLUGIN_LOG_PATTERNS):
        if not pattern.search(text):
            continue
        if idx < 2 or has_log_shape:
            return True
        if len(text) <= 180 and not CONVERSATIONAL_CUE_PATTERN.search(text):
            return True
    return False


def should_ignore_learning_sample(
    message_text: Any,
    *,
    sender_id: Optional[str] = None,
    is_bot: bool = False,
    source: Any = None,
    message_type: Any = None,
    event_type: Any = None,
    post_type: Any = None,
    sub_type: Any = None,
    notice_type: Any = None,
    plugin_name: Any = None,
    metadata: Any = None,
) -> bool:
    """Return true for messages that should not enter learning datasets."""
    text = _normalize_text(message_text)
    if not text:
        return True
    if has_system_event_metadata(
        source=source,
        message_type=message_type,
        event_type=event_type,
        post_type=post_type,
        sub_type=sub_type,
        notice_type=notice_type,
        plugin_name=plugin_name,
        metadata=metadata,
    ):
        return True
    if is_plugin_log_message(text):
        return True
    if is_bot or str(sender_id or "").lower() == "bot":
        return is_system_response(text)
    return is_command_message(text) or is_system_response(text)


def filter_learning_messages(messages: Iterable[Any]) -> List[Any]:
    """Filter dict/object messages before they are used for learning samples."""
    filtered: List[Any] = []
    for item in messages or []:
        if isinstance(item, dict):
            text = item.get("message", "")
            sender_id = item.get("sender_id")
            metadata = {key: item.get(key) for key in METADATA_FIELD_NAMES}
            metadata["metadata"] = item.get("metadata") or item.get("raw_event")
        else:
            text = getattr(item, "message", "")
            sender_id = getattr(item, "sender_id", None)
            metadata = {key: getattr(item, key, None) for key in METADATA_FIELD_NAMES}
            metadata["metadata"] = getattr(item, "metadata", None)
        if should_ignore_learning_sample(
            text,
            sender_id=sender_id,
            is_bot=str(sender_id or "").lower() == "bot",
            **metadata,
        ):
            continue
        filtered.append(item)
    return filtered
