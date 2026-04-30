"""Persona Anchor Retriever — query-aware dual-track few-shot retrieval."""
import asyncio
import json
import os
import time
from math import exp
from typing import List, Optional

import jieba
from astrbot.api import logger

from ...repositories.bot_message_repository import BotMessageRepository
from ...repositories.raw_message_repository import RawMessageRepository


class PersonaAnchorRetriever:
    """Query-aware dual-track few-shot retriever.

    Primary track: Current user's historical messages (learn real human style).
    Secondary track: Bot's own historical responses (persona consistency ref).
    """

    _METRIC_KEYS = [
        "total_calls",
        "successful_injections",
        "skips_disabled",
        "skips_insufficient",
        "skips_no_scored",
        "total_bot_samples",
        "total_user_samples",
        "total_relevance_score",
        "scored_count",
    ]

    def __init__(self, db_manager, config) -> None:
        self._db_manager = db_manager
        self._config = config
        self._metrics = self._default_metrics()
        self._metrics_lock = asyncio.Lock()
        self._load_metrics()

    @classmethod
    def _default_metrics(cls) -> dict:
        return {
            "total_calls": 0,
            "successful_injections": 0,
            "skips_disabled": 0,
            "skips_insufficient": 0,
            "skips_no_scored": 0,
            "total_bot_samples": 0,
            "total_user_samples": 0,
            "total_relevance_score": 0.0,
            "scored_count": 0,
            "injection_history": [],
        }

    async def retrieve(
        self,
        current_query: str,
        group_id: str,
        user_id: str,
    ) -> Optional[str]:
        """Return formatted few-shot text block; return None if insufficient samples.

        Primary track: user's historical messages (learn real human speaking style).
        Secondary track: Bot's own historical responses (persona consistency).
        """
        async with self._metrics_lock:
            self._metrics["total_calls"] += 1

        if not self._config.enable_persona_anchor:
            async with self._metrics_lock:
                self._metrics["skips_disabled"] += 1
            return None

        k_bot = self._config.persona_anchor_bot_k
        k_user = self._config.persona_anchor_user_k
        candidate_pool = self._config.persona_anchor_pool
        min_samples = self._config.persona_anchor_min_samples

        # Primary track: user's historical messages
        user_pool = await self._fetch_user_pool(group_id, user_id, candidate_pool)

        async with self._metrics_lock:
            self._metrics["total_user_samples"] += len(user_pool)

        if len(user_pool) < min_samples:
            logger.debug("[PersonaAnchor] insufficient user samples, skipped")
            async with self._metrics_lock:
                self._metrics["skips_insufficient"] += 1
                self._record_history(False, 0, len(user_pool), 0.0)
            return None

        # Secondary track: Bot historical responses
        bot_pool = await self._fetch_bot_pool(group_id, candidate_pool)

        async with self._metrics_lock:
            self._metrics["total_bot_samples"] += len(bot_pool)

        user_top = self._score_and_pick(current_query, user_pool, k_user)
        bot_top = self._score_and_pick(current_query, bot_pool, k_bot)

        # If scoring filters out all user messages, skip — user pool is primary.
        if not user_top:
            logger.debug("[PersonaAnchor] no scored user messages after filtering, skipped")
            async with self._metrics_lock:
                self._metrics["skips_no_scored"] += 1
                self._record_history(False, len(bot_pool), len(user_pool), 0.0)
            return None

        # Calculate average relevance score for user_top (primary track)
        avg_score = self._calc_avg_score(current_query, user_top)
        async with self._metrics_lock:
            self._metrics["total_relevance_score"] += avg_score
            self._metrics["scored_count"] += 1
            self._metrics["successful_injections"] += 1
            self._record_history(True, len(bot_pool), len(user_pool), avg_score)

        return self._format(user_top, bot_top)

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
                repo = RawMessageRepository(s)
                return await repo.get_recent_by_sender(group_id, user_id, limit)
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

    def _calc_avg_score(self, query: str, bot_top: list) -> float:
        if not query or not bot_top:
            return 0.0
        query_tokens = set(jieba.cut_for_search(query))
        if not query_tokens:
            return 0.0
        scores = []
        for msg in bot_top:
            text = msg.message
            if not text:
                continue
            msg_tokens = set(jieba.cut_for_search(text))
            overlap = len(query_tokens & msg_tokens)
            scores.append(overlap)
        return sum(scores) / len(scores) if scores else 0.0

    def _record_history(self, success: bool, bot_pool_size: int, user_pool_size: Optional[int], score: float) -> None:
        history = self._metrics["injection_history"]
        entry = {
            "ts": time.time(),
            "success": success,
            "bot_pool_size": bot_pool_size,
            "score": round(score, 2),
        }
        if user_pool_size is not None:
            entry["user_pool_size"] = user_pool_size
        history.append(entry)
        if len(history) > 100:
            history.pop(0)
        self.save_metrics()

    def get_metrics(self) -> dict:
        m = self._metrics
        total_calls = m["total_calls"]
        successful = m["successful_injections"]
        avg_bot = m["total_bot_samples"] / total_calls if total_calls > 0 else 0
        avg_user = m["total_user_samples"] / total_calls if total_calls > 0 else 0
        avg_score = m["total_relevance_score"] / m["scored_count"] if m["scored_count"] > 0 else 0
        injection_rate = successful / total_calls * 100 if total_calls > 0 else 0
        return {
            "enabled": getattr(self._config, 'enable_persona_anchor', False) if self._config else False,
            "total_calls": total_calls,
            "successful_injections": successful,
            "injection_rate": round(injection_rate, 1),
            "skips_disabled": m["skips_disabled"],
            "skips_insufficient": m["skips_insufficient"],
            "skips_no_scored": m["skips_no_scored"],
            "avg_bot_pool_size": round(avg_bot, 1),
            "avg_user_pool_size": round(avg_user, 1),
            "avg_relevance_score": round(avg_score, 2),
            "recent_history": [dict(h) for h in m["injection_history"]][-20:],
        }

    def reset_metrics(self) -> None:
        self._metrics = self._default_metrics()

    def _metrics_file(self) -> str:
        return os.path.join(self._config.data_dir, "persona_anchor_metrics.json")

    def save_metrics(self) -> None:
        try:
            with open(self._metrics_file(), "w", encoding="utf-8") as f:
                json.dump(self._metrics, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[PersonaAnchor] 保存指标失败: {e}")

    def _load_metrics(self) -> None:
        try:
            path = self._metrics_file()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # 只加载已知的键，防止 schema 变更导致问题
                for key in self._METRIC_KEYS:
                    if key in loaded:
                        self._metrics[key] = loaded[key]
                if "injection_history" in loaded:
                    self._metrics["injection_history"] = loaded["injection_history"]
                logger.info(f"[PersonaAnchor] 已恢复历史指标: {self._metrics['total_calls']} 次调用")
        except Exception as e:
            logger.warning(f"[PersonaAnchor] 加载指标失败: {e}")

    @staticmethod
    def _format(user_msgs: list, bot_msgs: list) -> str:
        """Format with user style as primary, Bot persona as secondary."""
        lines = ["[Speaking style reference — how this user typically talks]"]
        for msg in user_msgs:
            lines.append(f"User: {msg.message}")
        if bot_msgs:
            lines.append("")
            lines.append("[Your past responses in similar contexts]")
            for msg in bot_msgs:
                lines.append(f"You: {msg.message}")
        return "\n".join(lines)
