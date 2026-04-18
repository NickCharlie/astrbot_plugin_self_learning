"""Persona Anchor Retriever — query-aware dual-track few-shot retrieval."""
import time
from math import exp
from typing import List, Optional

import jieba
from astrbot.api import logger

from ...repositories.bot_message_repository import BotMessageRepository
from ...repositories.filtered_message_repository import FilteredMessageRepository


class PersonaAnchorRetriever:
    """Query-aware dual-track few-shot retriever.

    Primary track: Bot's own historical responses (persona anchoring)
    Secondary track: Current user's historical messages (natural conversation flow)
    """

    def __init__(self, db_manager, config) -> None:
        self._db_manager = db_manager
        self._config = config

    async def retrieve(
        self,
        current_query: str,
        group_id: str,
        user_id: str,
    ) -> Optional[str]:
        """Return formatted few-shot text block; return None if insufficient samples."""
        if not self._config.enable_persona_anchor:
            return None

        k_bot = self._config.persona_anchor_bot_k
        k_user = self._config.persona_anchor_user_k
        candidate_pool = self._config.persona_anchor_pool
        min_samples = self._config.persona_anchor_min_samples

        # Primary track: Bot historical responses
        bot_pool = await self._fetch_bot_pool(group_id, candidate_pool)
        if len(bot_pool) < min_samples:
            logger.debug("[PersonaAnchor] insufficient bot samples, skipped")
            return None

        # Secondary track: user's historical messages
        user_pool = await self._fetch_user_pool(group_id, user_id, candidate_pool)

        bot_top = self._score_and_pick(current_query, bot_pool, k_bot)
        user_top = self._score_and_pick(current_query, user_pool, k_user)

        # If scoring filters out all bot messages, skip persona anchoring entirely.
        # Returning a persona-anchored block with no bot messages would be misleading.
        if not bot_top:
            logger.debug("[PersonaAnchor] no scored bot messages after filtering, skipped")
            return None

        return self._format(bot_top, user_top)

    async def _fetch_bot_pool(self, group_id: str, limit: int) -> List:
        if not self._db_manager or not self._db_manager.engine:
            return []
        try:
            session = self._db_manager.engine.get_session()
            async with session as s:
                repo = BotMessageRepository(s)
                return await repo.get_recent_responses(group_id, limit)
        except Exception as e:
            logger.warning(f"[PersonaAnchor] bot pool fetch failed: {e}")
            return []

    async def _fetch_user_pool(self, group_id: str, user_id: str, limit: int) -> List:
        if not self._db_manager or not self._db_manager.engine:
            return []
        try:
            session = self._db_manager.engine.get_session()
            async with session as s:
                repo = FilteredMessageRepository(s)
                msgs = await repo.get_recent(group_id, limit)
                return [m for m in msgs if m.sender_id == user_id]
        except Exception as e:
            logger.warning(f"[PersonaAnchor] user pool fetch failed: {e}")
            return []

    def _score_and_pick(self, query: str, pool: list, k: int) -> list:
        if not query:
            return pool[:k]
        query_tokens = set(jieba.cut_for_search(query))
        if not query_tokens:
            return pool[:k]

        now = time.time()
        scored = []
        for msg in pool:
            text = msg.message
            if not text or len(text) < 3:
                continue
            msg_tokens = set(jieba.cut_for_search(text))
            overlap = len(query_tokens & msg_tokens)
            if overlap == 0:
                continue
            # Time decay: halve every 24 hours
            ts = msg.timestamp
            # Defensive: normalize if timestamp appears to be in milliseconds
            if ts > 1e12:
                ts = ts / 1000.0
            hours_ago = (now - ts) / 3600.0
            time_weight = exp(-hours_ago / 24.0)
            score = overlap * time_weight
            scored.append((score, msg))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:k]]

    @staticmethod
    def _format(bot_msgs: list, user_msgs: list) -> str:
        lines = ["[Persona Anchor — your past responses in similar contexts]"]
        for msg in bot_msgs:
            lines.append(f"You: {msg.message}")
        if user_msgs:
            lines.append("")
            lines.append("[How this user typically speaks]")
            for msg in user_msgs:
                lines.append(f"User: {msg.message}")
        return "\n".join(lines)
