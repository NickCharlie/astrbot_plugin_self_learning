"""Source-grounded human conversation samples shared by style learners."""

from __future__ import annotations

import math
import time
from datetime import datetime
from itertools import groupby
from typing import Any, Dict, Iterable, List, Optional

from .sample_filter import (
    extract_learning_message_metadata,
    should_ignore_learning_sample,
    strip_media_placeholders,
)


MAX_DIALOG_GAP_SECONDS = 300


def message_value(message: Any, name: str, default: Any = None) -> Any:
    """Read a field from either collected message representation."""
    if isinstance(message, dict):
        return message.get(name, default)
    return getattr(message, name, default)


def message_timestamp(message: Any) -> Optional[float]:
    value = message_value(message, "timestamp")
    try:
        number = value.timestamp() if isinstance(value, datetime) else float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def human_dialog_timeline(messages: Iterable[Any]) -> List[Any]:
    """Order recent rows chronologically, using DB IDs for same-second ties.

    Platform message IDs are not chronological. If a timestamp or a tied row's
    database ID is unavailable, preserve collection order rather than inventing
    an order that could move an excluded message out of a conversation boundary.
    """
    timeline = list(messages or [])
    if any(message_timestamp(message) is None for message in timeline):
        return timeline
    timeline.sort(key=message_timestamp)
    ordered = []
    for _, rows in groupby(timeline, key=message_timestamp):
        batch = list(rows)
        ids = [str(message_value(message, "id", "")) for message in batch]
        if all(database_id.isdecimal() for database_id in ids):
            batch = [message for _, message in sorted(
                zip(map(int, ids), batch), key=lambda item: item[0]
            )]
        ordered.extend(batch)
    return ordered


def is_human_learning_message(message: Any, group_id: str) -> bool:
    """Reject bot, cross-group, command, and non-chat messages."""
    sender = str(message_value(message, "sender_id", "") or "").strip()
    if not sender or sender.lower() in {"bot", "assistant", "system"}:
        return False
    source_group = str(message_value(message, "group_id", "") or "").strip()
    if source_group and source_group != str(group_id):
        return False

    metadata = message_value(message, "metadata")
    containers = [message]
    if isinstance(metadata, dict):
        containers.append(metadata)
    for container in containers:
        if any(
            str(message_value(container, key, "")).lower() in {"true", "1"}
            for key in ("is_bot", "is_self", "sender_is_bot", "is_bot_target")
        ):
            return False
        if str(message_value(container, "role", "")).lower() in {
            "bot", "assistant", "system", "tool",
        } or str(message_value(container, "platform", "")).lower() == "bot":
            return False

    text = strip_media_placeholders(message_value(message, "message", ""))
    if not any(character.isalnum() for character in text):
        return False
    return not should_ignore_learning_sample(
        text, sender_id=sender, **extract_learning_message_metadata(message)
    )


def extract_human_dialog_pairs(
    messages: Iterable[Any],
    group_id: str,
    *,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Extract adjacent human turns without bridging excluded messages.

    Timelines without timestamps retain collection order. Explicit replies must
    target the adjacent context message; otherwise adjacency is not evidence of
    a conversation between those two users.
    """
    timeline = human_dialog_timeline(messages)

    selected_user = str(user_id or "").strip()
    pairs: List[Dict[str, Any]] = []
    now = time.time()
    for context, response in zip(timeline, timeline[1:]):
        if not is_human_learning_message(context, group_id):
            continue
        if not is_human_learning_message(response, group_id):
            continue
        if message_value(response, "is_style_context", False) is True:
            continue
        sender = str(message_value(context, "sender_id")).strip()
        responder = str(message_value(response, "sender_id")).strip()
        if sender == responder or (selected_user and responder != selected_user):
            continue

        start, end = message_timestamp(context), message_timestamp(response)
        if start is not None and end is not None:
            if not 0 <= end - start <= MAX_DIALOG_GAP_SECONDS:
                continue
        reply_to = message_value(response, "reply_to")
        context_id = message_value(context, "message_id") or message_value(context, "id")
        if reply_to not in (None, ""):
            if context_id is None or str(reply_to) != str(context_id):
                continue

        situation = strip_media_placeholders(message_value(context, "message", ""))
        expression = strip_media_placeholders(message_value(response, "message", ""))
        if situation == expression:
            continue
        pairs.append({
            "situation": situation,
            "expression": expression,
            "group_id": str(group_id),
            "sender_id": responder,
            "context_sender_id": sender,
            "weight": 1.0,
            "confidence": 0.9 if reply_to not in (None, "") else 0.75,
            "last_active_time": now,
            "create_time": now,
        })
    return pairs
