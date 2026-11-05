"""Learning source scopes shared by message storage and sample extraction."""

from typing import Any, Iterable, List, Optional

try:
    from ..config import normalize_identifier_list, split_learning_blacklist
except ImportError:  # pragma: no cover - top-level plugin loading
    from config import normalize_identifier_list, split_learning_blacklist


def is_learning_blacklisted(
    sender_id: Any,
    group_id: Any,
    *,
    blocked_sender_ids: Iterable[str],
    blocked_group_ids: Iterable[str],
) -> bool:
    """单条消息是否命中学习黑名单。"""
    sender = str(sender_id or "").strip()
    group = str(group_id or "").strip()
    if sender and sender in set(blocked_sender_ids or []):
        return True
    if group and group in set(blocked_group_ids or []):
        return True
    return False


def mask_blacklisted_messages(
    messages: Iterable[Any], blacklist: Any, *, group_id: Optional[str] = None
) -> List[Any]:
    """Keep excluded turns as empty boundaries when building conversation pairs."""
    blocked_senders, blocked_groups = split_learning_blacklist(blacklist)
    if not blocked_senders and not blocked_groups:
        return list(messages or [])
    timeline = []
    for message in messages or []:
        fields = message if isinstance(message, dict) else vars(message)
        if is_learning_blacklisted(
            fields.get("sender_id"), fields.get("group_id") or group_id,
            blocked_sender_ids=blocked_senders,
            blocked_group_ids=blocked_groups,
        ):
            timeline.append({**fields, "message": ""})
        else:
            timeline.append(message)
    return timeline


def mark_style_context_messages(
    messages: Iterable[Any], targets: Any, *, group_id: Optional[str] = None,
) -> List[Any]:
    """Keep non-target speakers as context, never as learned response examples."""
    target_ids = set(normalize_identifier_list(targets, full_learning_markers=True))
    if not target_ids:
        return list(messages or [])
    marked = []
    for message in messages or []:
        fields = message if isinstance(message, dict) else vars(message)
        source_group = str(fields.get("group_id") or group_id or "")
        sender_id = str(fields.get("sender_id") or "")
        if sender_id not in target_ids and f"group_{source_group}" not in target_ids:
            marked.append({**fields, "is_style_context": True})
        else:
            marked.append(message)
    return marked
