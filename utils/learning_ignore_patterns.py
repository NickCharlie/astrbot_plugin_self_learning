"""User-configurable learning ignore regexes (issue #315).

媒体解析类插件的出站卡片与入站裸引用（BV 号 / b23.tv 链接）没有学习价值。
管理员可以在 ``Target_Settings.learning_ignore_patterns`` 里配置正则，命中即
视为非学习样本，入站与出站都生效。

放在 ``utils`` 而不是 ``services.learning`` 是有意为之：WebUI 与 Hub 在测试
环境里会以顶层 ``services`` 包导入，而 ``services.learning.__init__`` 依赖
插件包内的相对导入；轻量模块避免把过滤能力绑在那个导入链上。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Tuple

from astrbot.api import logger

_LOGGER = logger

_CUSTOM_IGNORE_PATTERNS: Tuple[re.Pattern[str], ...] = ()

# 正则只匹配消息前缀：聊天样本远短于该长度，同时限制回溯爆炸时的最坏工作量。
# 规则由管理员在插件配置里填写，属于可信输入；这里仍做长度上限兜底。
_MAX_IGNORE_PATTERN_INPUT = 2000


def configure_learning_ignore_patterns(patterns: Any) -> int:
    """编译用户配置的学习忽略正则，返回实际生效的规则数量。

    空行与空白规则会被忽略；无效正则（含超大重复次数）记录告警后跳过，
    不影响其余规则。传 ``None`` 或空列表可清空全部规则。
    """
    global _CUSTOM_IGNORE_PATTERNS
    if patterns is None:
        raw_patterns: Iterable[Any] = ()
    elif isinstance(patterns, str):
        raw_patterns = patterns.splitlines()
    else:
        raw_patterns = patterns

    compiled: List[re.Pattern[str]] = []
    for raw in raw_patterns:
        pattern = str(raw or "").strip()
        if not pattern:
            continue
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except (re.error, OverflowError) as exc:
            _LOGGER.warning(f"自定义学习忽略正则无效，已跳过: {pattern!r} ({exc})")
    _CUSTOM_IGNORE_PATTERNS = tuple(compiled)
    return len(_CUSTOM_IGNORE_PATTERNS)


def matches_learning_ignore_pattern(message_text: Any) -> bool:
    """文本命中任一自定义忽略正则时返回 True。"""
    if not _CUSTOM_IGNORE_PATTERNS:
        return False
    text = "" if message_text is None else str(message_text).strip()
    text = text[:_MAX_IGNORE_PATTERN_INPUT]
    return any(pattern.search(text) for pattern in _CUSTOM_IGNORE_PATTERNS)
