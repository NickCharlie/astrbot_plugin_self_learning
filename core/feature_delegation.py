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

    def __init__(self, config: Any, context: Any) -> None:
        self._config = config
        self._context = context
        self._last_status: tuple[bool, bool] | None = None

    def memory_plugin(self) -> Optional[Any]:
        aliases = (
            getattr(self._config, "livingmemory_plugin_name", None),
            *self.LIVING_MEMORY_ALIASES,
        )
        return self._find_active_star(aliases)

    def reply_plugin(self) -> Optional[Any]:
        aliases = (
            getattr(self._config, "group_chat_plus_plugin_name", None),
            *self.GROUP_CHAT_PLUS_ALIASES,
        )
        return self._find_active_star(aliases)

    def should_delegate_memory(self) -> bool:
        if not getattr(self._config, "delegate_memory_to_livingmemory", True):
            return False
        if not getattr(self._config, "disable_local_memory_when_delegated", True):
            return False
        return self.memory_plugin() is not None

    def should_delegate_reply(self) -> bool:
        if not getattr(self._config, "delegate_reply_to_group_chat_plus", True):
            return False
        if not getattr(self._config, "disable_local_reply_when_delegated", True):
            return False
        return self.reply_plugin() is not None

    def status(self) -> dict[str, Any]:
        memory_plugin = self.memory_plugin()
        reply_plugin = self.reply_plugin()
        return {
            "memory_delegated": self.should_delegate_memory(),
            "memory_plugin": self._star_label(memory_plugin),
            "reply_delegated": self.should_delegate_reply(),
            "reply_plugin": self._star_label(reply_plugin),
        }

    def log_status(self) -> None:
        status = self.status()
        current = (status["memory_delegated"], status["reply_delegated"])
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
            logger.info(
                "[功能融合] 回复决策和回复生成已委托给 "
                f"{status['reply_plugin']}，本插件仅注入学习上下文"
            )
        else:
            logger.info("[功能融合] 未检测到可用 Group Chat Plus，保留本插件本地回复兼容能力")

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
