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
from ...utils.persona_selection import normalize_persona_scope
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
    """Persist manually selected conversation context into learning stores.

    When long-term memory is delegated to LivingMemory, the explicit
    ``remember`` write goes to LivingMemory's ``MemoryEngine.add_memory``
    instead of the local ``memories`` table (LivingMemory 2.8.x public API).
    Expression/exemplar/review stores stay local because they are learning
    artifacts owned by this plugin.
    """

    def __init__(
        self,
        db_manager: Any,
        embedding_provider: Any = None,
        feature_delegation: Any = None,
        group_id_to_unified_origin: Optional[Dict[str, str]] = None,
        context: Any = None,
        plugin_config: Any = None,
    ) -> None:
        self._db = db_manager
        self._embedding_provider = embedding_provider
        self._feature_delegation = feature_delegation
        self._group_id_to_unified_origin = group_id_to_unified_origin or {}
        self._context = context
        self._config = plugin_config

    async def remember(
        self,
        *,
        group_id: str,
        sender_id: str,
        content: str,
        persona_id: str = "default",
        unified_origin: Optional[str] = None,
    ) -> RememberResult:
        """Store a remembered snippet and link it to style-learning stores."""
        content = self._clean_command_payload(content)
        if not content:
            raise ValueError("remember 内容不能为空")

        situation, expression = self._parse_pair(content)
        if not expression:
            expression = situation

        self._validate_sample(situation, expression)
        persona_id = normalize_persona_scope(persona_id)

        result = RememberResult()
        delegated_id = await self._remember_via_livingmemory(
            group_id=group_id,
            sender_id=sender_id,
            content=content,
            unified_origin=unified_origin,
        )
        if delegated_id is not None:
            result.memory_id = delegated_id
        else:
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
                persona_id=persona_id,
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

    async def _remember_via_livingmemory(
        self,
        *,
        group_id: str,
        sender_id: str,
        content: str,
        unified_origin: Optional[str] = None,
    ) -> Optional[int]:
        """Write the snippet through LivingMemory when memory is delegated.

        Returns the LivingMemory memory id, or ``None`` to fall back to the
        local ``memories`` table.
        """
        delegation = self._feature_delegation
        if not delegation or not hasattr(delegation, "should_delegate_memory"):
            return None
        try:
            if not delegation.should_delegate_memory():
                return None
            star = delegation.memory_plugin()
        except Exception as exc:
            logger.debug(f"remember 检测 LivingMemory 失败: {exc}")
            return None

        plugin = getattr(star, "star_cls", None)
        initializer = getattr(plugin, "initializer", None)
        memory_engine = (
            getattr(initializer, "memory_engine", None)
            or getattr(plugin, "memory_engine", None)
        )
        add_memory = getattr(memory_engine, "add_memory", None)
        if not callable(add_memory):
            logger.debug("LivingMemory memory_engine 尚未就绪，remember 回退本地记忆")
            return None

        cfg = self._livingmemory_config_getter(plugin)
        if not self._is_livingmemory_allowed(
            cfg,
            group_id=group_id,
            sender_id=sender_id,
            unified_origin=unified_origin
            or self._group_id_to_unified_origin.get(group_id),
        ):
            logger.debug("remember 被 LivingMemory 访问控制拒绝，回退本地记忆")
            return None

        base_session = unified_origin or self._group_id_to_unified_origin.get(group_id)
        if not base_session:
            logger.debug(
                "remember 缺少 unified_msg_origin，回退本地记忆以避免写入不可召回的 LivingMemory 数据"
            )
            return None

        use_persona_filtering = bool(
            cfg("filtering_settings.use_persona_filtering", True)
        )
        livingmemory_persona_id = await self._resolve_livingmemory_persona_id(
            group_id=group_id,
            unified_origin=base_session,
        )
        if use_persona_filtering and not livingmemory_persona_id:
            logger.warning(
                "remember 无法解析 AstrBot 人格 ID，回退本地记忆以避免写入不可召回的 LivingMemory 数据"
            )
            return None

        session_id = self._resolve_livingmemory_session_id(
            plugin=plugin,
            group_id=group_id,
            unified_origin=unified_origin,
            sender_id=sender_id,
        )
        try:
            memory_id = await add_memory(
                content,
                session_id=session_id,
                persona_id=livingmemory_persona_id,
                importance=0.9,
                metadata={
                    "memory_origin": "self_learning_remember",
                    "memorize_reason": "用户在 Self Learning 中显式 remember 的对话片段",
                    "source": "self_learning_remember",
                    "sender_id": sender_id,
                    "group_id": group_id,
                },
            )
        except Exception as exc:
            logger.warning(f"remember 写入 LivingMemory 失败，回退本地记忆: {exc}")
            return None

        if isinstance(memory_id, int) and memory_id > 0:
            logger.info(
                "remember 已写入 LivingMemory: memory_id=%s, session=%s",
                memory_id,
                session_id,
            )
            return memory_id
        return None

    async def _resolve_livingmemory_persona_id(
        self,
        *,
        group_id: str,
        unified_origin: str,
    ) -> Optional[str]:
        """Resolve AstrBot persona id expected by LivingMemory filtering.

        ``remember`` receives the expression-pattern isolation key (bot account
        id) from the command handler; LivingMemory stores the AstrBot persona id
        in metadata and filters recall by strict equality, so the two must not
        be mixed.
        """
        context = self._context
        persona_manager = getattr(context, "persona_manager", None) if context else None
        if not persona_manager:
            return None
        try:
            from ...utils.persona_selection import (
                get_persona_identifier,
                resolve_target_persona,
            )

            persona = await resolve_target_persona(
                persona_manager,
                self._config,
                unified_origin or group_id,
                require_existing=False,
                log=logger,
            )
        except Exception as exc:
            logger.debug(f"remember 解析 AstrBot 人格失败: {exc}")
            return None
        if not persona:
            return None
        return get_persona_identifier(persona)

    def _resolve_livingmemory_session_id(
        self,
        *,
        plugin: Any,
        group_id: str,
        unified_origin: Optional[str],
        sender_id: str,
    ) -> Optional[str]:
        """Mirror LivingMemory 2.8.x ``resolve_memory_scope`` for explicit writes.

        LivingMemory resolves storage/retrieval scope from the host config
        (``filtering_settings.memory_scope_mode``). Direct ``add_memory`` calls
        bypass that resolver, so the remember path reproduces its mode mapping:
        ``session`` → UMO, ``user`` → platform user scope, ``global`` → global
        scope, ``legacy`` → session filter toggle.
        """
        session_id = (
            unified_origin
            or self._group_id_to_unified_origin.get(group_id)
            or group_id
        )

        config_manager = getattr(plugin, "config_manager", None)
        getter = getattr(config_manager, "get", None)

        def _cfg(key: str, default: Any = None) -> Any:
            if callable(getter):
                try:
                    return getter(key, default)
                except Exception:
                    return default
            return default

        isolated_raw = _cfg("filtering_settings.isolated_sessions", "") or ""
        isolated_sessions = {
            item.strip()
            for item in re.split(r"[,;\n]", str(isolated_raw))
            if item.strip()
        }
        if session_id and session_id in isolated_sessions:
            return session_id

        mode = str(
            _cfg("filtering_settings.memory_scope_mode", "legacy")
        ).casefold()
        if mode == "session":
            return session_id
        if mode == "global":
            return "livingmemory:global"
        if mode == "user":
            platform = ""
            if isinstance(session_id, str) and ":" in session_id:
                platform = session_id.split(":", 1)[0].casefold()
            alias = self._resolve_identity_alias(_cfg, platform, sender_id)
            identity = (alias or str(sender_id or "")).casefold()
            return f"livingmemory:user:{platform or 'unknown'}:{identity}"

        use_session = bool(
            _cfg("filtering_settings.use_session_filtering", True)
        )
        if use_session:
            return session_id
        return "livingmemory:global" if isolated_sessions else None

    @staticmethod
    def _livingmemory_config_getter(plugin: Any):
        config_manager = getattr(plugin, "config_manager", None)
        getter = getattr(config_manager, "get", None)

        def _cfg(key: str, default: Any = None) -> Any:
            if callable(getter):
                try:
                    return getter(key, default)
                except Exception:
                    return default
            return default

        return _cfg

    @staticmethod
    def _is_livingmemory_allowed(
        cfg,
        *,
        group_id: str,
        sender_id: str,
        unified_origin: Optional[str],
    ) -> bool:
        """Respect LivingMemory's ``access_control`` allowlist for external writes."""
        if not bool(cfg("access_control.whitelist_enabled", False)):
            return True

        raw_allowed = cfg("access_control.allowed_ids", "") or ""
        allowed = {
            item.strip().casefold()
            for item in re.split(r"[,;\n]", str(raw_allowed))
            if item.strip()
        }
        if not allowed:
            return False

        platform = ""
        if isinstance(unified_origin, str) and ":" in unified_origin:
            platform = unified_origin.split(":", 1)[0]

        alias = RememberService._resolve_identity_alias(cfg, platform, sender_id)
        candidates = {
            str(group_id or ""),
            str(sender_id or ""),
            str(unified_origin or ""),
            f"{platform}:{sender_id}" if platform and sender_id else "",
            str(alias or ""),
        }
        return any(
            candidate and candidate.casefold() in allowed
            for candidate in candidates
        )

    @staticmethod
    def _resolve_identity_alias(cfg, platform: str, sender_id: str) -> Optional[str]:
        """Mirror LivingMemory ``identity_aliases`` (source=canonical)."""
        raw = cfg("access_control.identity_aliases", "") or ""
        aliases = {}
        for line in str(raw).splitlines():
            source, separator, target = line.partition("=")
            if not separator:
                continue
            source = source.strip()
            target = target.strip()
            if source and target:
                aliases[source.casefold()] = target
        candidates = (
            f"{platform}:{sender_id}" if platform and sender_id else "",
            str(sender_id or ""),
        )
        for candidate in candidates:
            if candidate and candidate.casefold() in aliases:
                return aliases[candidate.casefold()]
        return None

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
        persona_id: str = "default",
        situation: str,
        expression: str,
    ) -> bool:
        from ...models.orm.expression import ExpressionPattern

        now = time.time()
        persona_id = normalize_persona_scope(persona_id)
        record = ExpressionPattern(
            group_id=group_id,
            persona_id=persona_id,
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
