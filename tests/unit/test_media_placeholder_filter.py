"""Regression tests for media placeholder filtering.

ChatPlus 1.2.x renders quoted images as ``[引用 >>> 昵称(ID:x): [图片]]``.
Those text-only placeholders must not enter expression samples, while the
plain-text part of a mixed message must be preserved.
"""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.learning.sample_filter import (  # noqa: E402
    filter_learning_messages,
    is_media_only_message,
    should_ignore_learning_sample,
    strip_media_placeholders,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "[图片]",
        "[表情]",
        "[CQ:image,file=abc.jpg]",
        "[引用 >>> 小明(123): [图片]]",
        "[引用 >>> 小明(123): [表情]]",
    ],
)
def test_media_only_messages_are_detected(text):
    assert is_media_only_message(text) is True
    assert strip_media_placeholders(text) == ""
    assert should_ignore_learning_sample(text) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[图片] 今天好开心", "今天好开心"),
        ("[引用 >>> 小明(123): 你好 [图片]]", "你好"),
        ("[引用 >>> A(ID:1): 你好] 后面的话", "你好 后面的话"),
        ("[引用 >>> A: 你好: 世界] 后面", "你好: 世界 后面"),
        ("hello <img src='/a.png'> world", "hello  world"),
    ],
)
def test_mixed_messages_keep_text(text, expected):
    assert strip_media_placeholders(text) == expected
    assert is_media_only_message(text) is False


@pytest.mark.unit
def test_filter_learning_messages_drops_media_and_cleans_text():
    messages = [
        {"sender_id": "u1", "message": "[图片]"},
        {"sender_id": "u1", "message": "[图片] 今天好开心"},
        {"sender_id": "u1", "message": "普通聊天"},
    ]

    result = filter_learning_messages(messages)

    assert [item["message"] for item in result] == ["今天好开心", "普通聊天"]


@pytest.mark.unit
def test_filter_learning_messages_cleans_object_messages():
    first = SimpleNamespace(sender_id="u1", message="[图片]")
    second = SimpleNamespace(sender_id="u1", message="[图片] 晚安")

    result = filter_learning_messages([first, second])

    assert result == [second]
    assert second.message == "晚安"


@pytest.mark.unit
def test_plugin_runtime_logs_from_chatplus_are_ignored():
    assert should_ignore_learning_sample(
        "[INFO] [GroupChatPlus] 读空气判断完成"
    ) is True
    assert should_ignore_learning_sample(
        "[INFO] [astrbot_plugin_group_chat_plus] 主动对话已启动"
    ) is True
    assert should_ignore_learning_sample("GroupChatPlus 这个插件真好用") is False
