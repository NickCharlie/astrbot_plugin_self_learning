"""Runtime feature delegation between self-learning and companion plugins."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from astrbot.api import logger


class FeatureDelegation:
    """Detect external companion plugins and decide which local features to skip.

    The self-learning plugin remains responsible for learning, review, jargon,
    style examples and prompt enrichment. Long-term memory and reply ownership can
    be delegated to specialized plugins when they are loaded in AstrBot.
    """

    LIVING_MEMORY_ALIASES = ("LivingMemory", "astrbot_plugin_livingmemory")
    GROUP_CHAT_PLUS_ALIASES = (
        "astrbot_plugin_group_chat_plus",
        "Group Chat Plus",
        "ChatPlus",
    )
    LIVINGHELLO_ALIASES = (
        "astrbot_plugin_LivingHello",
        "LivingHello",
    )

    REPLY_KIND_GROUP_CHAT_PLUS = "group_chat_plus"
    REPLY_KIND_LIVINGHELLO = "livinghello"

    def __init__(self, config: Any, context: Any) -> None:
        self._config = config
        self._context = context
        self._last_status: tuple[bool, bool, Optional[str]] | None = None

    def memory_plugin(self) -> Optional[Any]:
        aliases = (
            getattr(self._config, "livingmemory_plugin_name", None),
            *self.LIVING_MEMORY_ALIASES,
        )
        return self._find_active_star(aliases)

    def group_chat_plus_plugin(self) -> Optional[Any]:
        aliases = (
            getattr(self._config, "group_chat_plus_plugin_name", None),
            *self.GROUP_CHAT_PLUS_ALIASES,
        )
        return self._find_active_star(aliases)

    def livinghello_plugin(self) -> Optional[Any]:
        aliases = (
            getattr(self._config, "livinghello_plugin_name", None),
            *self.LIVINGHELLO_ALIASES,
        )
        return self._find_active_star(aliases)

    def group_chat_plus_delegation_enabled(self) -> bool:
        return bool(
            getattr(self._config, "delegate_reply_to_group_chat_plus", True)
        )

    def livinghello_delegation_enabled(self) -> bool:
        return bool(
            getattr(self._config, "delegate_reply_to_livinghello", False)
        )

    def reply_plugin_kind(self) -> Optional[str]:
        """返回当前生效的回复委托目标。

        Group Chat Plus 与 LivingHello 同时加载时，Group Chat Plus 只在自身
        委托开关开启时才优先；关闭 Group Chat Plus 委托后，已开启委托的
        LivingHello 可以接管。两个目标都未启用委托时仍返回检测到的插件，
        供功能融合页展示，但不应被当成已委托。
        """
        group_chat_plus = self.group_chat_plus_plugin()
        livinghello = self.livinghello_plugin()
        if group_chat_plus is not None and self.group_chat_plus_delegation_enabled():
            return self.REPLY_KIND_GROUP_CHAT_PLUS
        if livinghello is not None and self.livinghello_delegation_enabled():
            return self.REPLY_KIND_LIVINGHELLO
        if group_chat_plus is not None:
            return self.REPLY_KIND_GROUP_CHAT_PLUS
        if livinghello is not None:
            return self.REPLY_KIND_LIVINGHELLO
        return None

    def reply_plugin(self) -> Optional[Any]:
        """返回当前生效的回复委托目标；未启用委托时返回检测到的插件。"""
        return self._reply_plugin_for_kind(self.reply_plugin_kind())

    def reply_delegation(self) -> tuple[Optional[str], Optional[Any]]:
        """一次性返回委托目标类型与插件，供决策和日志共用。

        调用方拿到结果后应同时用于 ``should_delegate_reply(kind)`` 和日志，
        避免两次查询之间插件注册表变化导致目标不一致。
        """
        kind = self.reply_plugin_kind()
        return kind, self._reply_plugin_for_kind(kind)

    def _reply_plugin_for_kind(self, kind: Optional[str]) -> Optional[Any]:
        if kind == self.REPLY_KIND_GROUP_CHAT_PLUS:
            return self.group_chat_plus_plugin()
        if kind == self.REPLY_KIND_LIVINGHELLO:
            return self.livinghello_plugin()
        return None

    def should_delegate_memory(self) -> bool:
        if not getattr(self._config, "delegate_memory_to_livingmemory", True):
            return False
        if not getattr(self._config, "disable_local_memory_when_delegated", True):
            return False
        return self.memory_plugin() is not None

    def should_delegate_reply(self, kind: Optional[str] = None) -> bool:
        """判断是否跳过本地回复器。

        ``kind`` 可由调用方预先取得并复用，避免检测决策与日志之间插件注册表
        变化导致目标不一致。
        """
        if not getattr(self._config, "disable_local_reply_when_delegated", True):
            return False

        if kind is None:
            kind = self.reply_plugin_kind()
        if kind == self.REPLY_KIND_GROUP_CHAT_PLUS:
            return (
                self.group_chat_plus_plugin() is not None
                and self.group_chat_plus_delegation_enabled()
            )
        if kind == self.REPLY_KIND_LIVINGHELLO:
            # LivingHello 只做接话判定与静默否决，默认不接管，需显式开启
            return (
                self.livinghello_plugin() is not None
                and self.livinghello_delegation_enabled()
            )
        return False

    def status(self) -> dict[str, Any]:
        memory_plugin = self.memory_plugin()
        reply_kind, reply_plugin = self.reply_delegation()
        return {
            "memory_delegated": self.should_delegate_memory(),
            "memory_plugin": self._star_label(memory_plugin),
            "reply_delegated": self.should_delegate_reply(reply_kind),
            "reply_plugin": self._star_label(reply_plugin),
            "reply_plugin_kind": reply_kind,
        }

    def log_status(self) -> None:
        status = self.status()
        current = (
            status["memory_delegated"],
            status["reply_delegated"],
            status["reply_plugin_kind"],
        )
        if current == self._last_status:
            return
        self._last_status = current

        if status["memory_delegated"]:
            logger.info(
                "[功能融合] 记忆能力已委托给 "
                f"{status['memory_plugin']}，本插件跳过本地长期记忆写入/注入"
            )
        else:
            logger.info("[功能融合] 未检测到可用 LivingMemory，保留本插件本地记忆能力")

        if status["reply_delegated"]:
            if status["reply_plugin_kind"] == self.REPLY_KIND_LIVINGHELLO:
                logger.info(
                    "[功能融合] 回复决策已委托给 "
                    f"{status['reply_plugin']}，本插件跳过本地回复器；"
                    "回复正文仍由宿主默认对话链路生成"
                )
            else:
                logger.info(
                    "[功能融合] 回复决策和回复生成已委托给 "
                    f"{status['reply_plugin']}，本插件仅注入学习上下文"
                )
        else:
            logger.info(
                "[功能融合] 未启用外部回复决策委托"
                "（Group Chat Plus / LivingHello），保留本插件本地回复兼容能力"
            )

    def _find_active_star(self, aliases: Iterable[Any]) -> Optional[Any]:
        raw_aliases = [
            str(alias).strip()
            for alias in aliases
            if str(alias or "").strip()
        ]
        wanted = {alias.lower() for alias in raw_aliases}
        if not wanted or not self._context:
            return None

        getter = getattr(self._context, "get_registered_star", None)
        if callable(getter):
            for alias in raw_aliases:
                try:
                    star = getter(alias)
                except Exception:
                    star = None
                if self._is_active_star(star):
                    return star

        all_stars_getter = getattr(self._context, "get_all_stars", None)
        if not callable(all_stars_getter):
            return None

        try:
            stars = all_stars_getter() or []
        except Exception:
            return None

        for star in stars:
            if not self._is_active_star(star):
                continue
            candidates = {
                getattr(star, "name", None),
                getattr(star, "display_name", None),
                getattr(star, "root_dir_name", None),
                getattr(star, "module_path", None),
            }
            module_path = getattr(star, "module_path", None)
            if isinstance(module_path, str):
                parts = [part for part in module_path.split(".") if part]
                candidates.update(parts)
            normalized = {
                str(candidate).strip().lower()
                for candidate in candidates
                if str(candidate or "").strip()
            }
            if normalized & wanted:
                return star
        return None

    @staticmethod
    def _is_active_star(star: Any) -> bool:
        if not star:
            return False
        if getattr(star, "activated", True) is False:
            return False
        return getattr(star, "star_cls", None) is not None

    @staticmethod
    def _star_label(star: Any) -> Optional[str]:
        if not star:
            return None
        return (
            getattr(star, "display_name", None)
            or getattr(star, "name", None)
            or getattr(star, "root_dir_name", None)
            or getattr(star, "module_path", None)
        )
