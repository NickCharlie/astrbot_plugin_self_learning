"""Manual remember command support.

The command stores an explicit user-selected snippet as memory and, when
possible, links it into expression patterns and few-shot exemplars.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from astrbot.api import logger

from ...constants import UPDATE_TYPE_STYLE_LEARNING
from .sample_filter import should_ignore_learning_sample


_PAIR_SEPARATORS = (
    "=>",
    "->",
    "→",
    "回复：",
    "回答：",
    "回应：",
    "\nB:",
    "\nBot:",
)


@dataclass
class RememberResult:
    """Result summary for manual remember ingestion."""

    memory_id: int = 0
    expression_saved: bool = False
    exemplar_id: Optional[int] = None
    style_review_id: int = 0


class RememberService:
    """Persist manually selected conversation context into learning stores."""

    def __init__(
        self,
        db_manager: Any,
        embedding_provider: Any = None,
    ) -> None:
        self._db = db_manager
        self._embedding_provider = embedding_provider

    async def remember(
        self,
        *,
        group_id: str,
        sender_id: str,
        content: str,
    ) -> RememberResult:
        """Store a remembered snippet and link it to style-learning stores."""
        content = self._clean_command_payload(content)
        if not content:
            raise ValueError("remember 内容不能为空")

        situation, expression = self._parse_pair(content)
        if not expression:
            expression = situation

        self._validate_sample(situation, expression)

        result = RememberResult()
        result.memory_id = await self._db.save_manual_memory(
            group_id=group_id,
            user_id=sender_id,
            content=content,
            memory_type="manual_remember",
            importance=9,
        )
        async with self._db.get_session() as session:
            expression_saved = await self._save_expression_pattern(
                session,
                group_id=group_id,
                situation=situation,
                expression=expression,
            )
            await session.commit()
            result.expression_saved = expression_saved

        result.exemplar_id = await self._save_exemplar(
            content=self._format_exemplar(situation, expression),
            group_id=group_id,
            sender_id=sender_id,
        )
        result.style_review_id = await self._save_style_review(
            group_id=group_id,
            situation=situation,
            expression=expression,
            content=content,
        )
        return result

    @staticmethod
    def _clean_command_payload(content: str) -> str:
        return (content or "").strip()

    @staticmethod
    def _parse_pair(content: str) -> tuple[str, str]:
        text = content.strip()
        for separator in _PAIR_SEPARATORS:
            if separator not in text:
                continue
            before, after = text.split(separator, 1)
            return before.strip(" \n\r\tA:用户：User:"), after.strip()

        quoted = re.findall(r"[「“\"]([^」”\"]+)[」”\"]", text)
        if len(quoted) >= 2:
            return quoted[0].strip(), quoted[1].strip()
        return text, ""

    @staticmethod
    def _validate_sample(situation: str, expression: str) -> None:
        if len(situation.strip()) < 2:
            raise ValueError("引用内容太短，无法学习")
        if len(expression.strip()) < 2:
            raise ValueError("表达示例太短，无法学习")
        if should_ignore_learning_sample(situation):
            raise ValueError("引用内容像命令或系统输出，已跳过")
        if should_ignore_learning_sample(expression, sender_id="bot", is_bot=True):
            raise ValueError("表达示例像命令帮助或系统输出，已跳过")

    async def _save_expression_pattern(
        self,
        session: Any,
        *,
        group_id: str,
        situation: str,
        expression: str,
    ) -> bool:
        from ...models.orm.expression import ExpressionPattern

        now = time.time()
        record = ExpressionPattern(
            group_id=group_id,
            situation=situation[:300],
            expression=expression[:500],
            weight=2.0,
            last_active_time=now,
            create_time=now,
        )
        session.add(record)
        return True

    async def _save_exemplar(
        self,
        *,
        content: str,
        group_id: str,
        sender_id: str,
    ) -> Optional[int]:
        try:
            from ..integration.exemplar_library import ExemplarLibrary

            library = ExemplarLibrary(self._db, self._embedding_provider)
            return await library.add_exemplar(content, group_id, sender_id)
        except Exception as exc:
            logger.warning(f"remember 保存对话示例失败: {exc}", exc_info=True)
            return None

    async def _save_style_review(
        self,
        *,
        group_id: str,
        situation: str,
        expression: str,
        content: str,
    ) -> int:
        review_data: Dict[str, Any] = {
            "type": UPDATE_TYPE_STYLE_LEARNING,
            "group_id": group_id,
            "timestamp": time.time(),
            "learned_patterns": [
                {
                    "situation": situation,
                    "expression": expression,
                    "weight": 2.0,
                    "confidence": 0.95,
                }
            ],
            "few_shots_content": self._build_few_shots(situation, expression),
            "description": "手动 remember 命令记录的对话风格样例",
            "metadata": {
                "source": "remember_command",
                "original_content": content,
                "created_at": datetime.utcnow().isoformat(),
            },
        }
        try:
            return await self._db.create_style_learning_review(review_data)
        except Exception as exc:
            logger.warning(f"remember 创建风格审查记录失败: {exc}", exc_info=True)
            return 0

    @staticmethod
    def _build_few_shots(situation: str, expression: str) -> str:
        return (
            "*Here are few shots of dialogs, you need to imitate the tone of 'B' "
            "in the following dialogs to respond:\n"
            f"A: {situation}\n"
            f"B: {expression}"
        )

    @staticmethod
    def _format_exemplar(situation: str, expression: str) -> str:
        if situation == expression:
            return expression
        return f"A: {situation}\nB: {expression}"
