"""Jargon learning module.

Keeps jargon trigger accounting and mining work outside the main message
pipeline. The pipeline still owns task tracking and event sequencing.
"""

from typing import Any, Dict, Optional, Set

from astrbot.api import logger

from ..monitoring.instrumentation import monitored
from .sample_filter import filter_learning_messages


class JargonLearningModule:
    """Coordinate jargon statistical updates, triggers, and mining."""

    def __init__(
        self,
        *,
        config: Any,
        message_collector: Any,
        jargon_miner_manager: Optional[Any],
        jargon_statistical_filter: Optional[Any],
        db_manager: Any,
    ) -> None:
        self._config = config
        self._message_collector = message_collector
        self._jargon_miner_manager = jargon_miner_manager
        self._jargon_statistical_filter = jargon_statistical_filter
        self._db_manager = db_manager

        self.active_groups: Set[str] = set()
        self.last_trigger_counts: Dict[str, int] = {}
        self.group_raw_message_counts: Dict[str, int] = {}
        self.groups_seeded: set[str] = set()

    def update_statistical_filter(
        self,
        message_text: str,
        group_id: str,
        sender_id: str,
    ) -> None:
        """Update the cheap statistical pre-filter for one message."""
        if not self._config.enable_jargon_learning:
            return
        if not self._jargon_statistical_filter:
            return
        try:
            self._jargon_statistical_filter.update_from_message(
                message_text, group_id, sender_id
            )
        except Exception:
            pass  # best-effort

    def note_collected_message(self, group_id: str) -> None:
        """Track in-memory raw message count after collection succeeds."""
        self.group_raw_message_counts[group_id] = (
            self.group_raw_message_counts.get(group_id, 0) + 1
        )

    @monitored
    async def get_raw_message_count(self, group_id: str) -> int:
        """Get raw message count for a group, seeded from DB once."""
        if group_id not in self.groups_seeded:
            try:
                stats = await self._message_collector.get_statistics(group_id)
                db_count = stats.get("raw_messages", 0)
                memory_count = self.group_raw_message_counts.get(group_id, 0)
                self.group_raw_message_counts[group_id] = max(db_count, memory_count)
            except Exception:
                pass
            self.groups_seeded.add(group_id)
        return self.group_raw_message_counts.get(group_id, 0)

    def should_schedule_mining(self, group_id: str, raw_message_count: int) -> bool:
        """Trigger jargon mining once per additional 10 messages per group."""
        if raw_message_count < 10:
            return False
        if group_id in self.active_groups:
            return False
        last_trigger = self.last_trigger_counts.get(group_id, 0)
        return raw_message_count - last_trigger >= 10

    def mark_mining_started(self, group_id: str, raw_message_count: int) -> None:
        """Record trigger state before spawning a mining task."""
        self.last_trigger_counts[group_id] = raw_message_count
        self.active_groups.add(group_id)

    def mark_mining_finished(self, group_id: str) -> None:
        """Clear active mining state for a group."""
        self.active_groups.discard(group_id)

    @monitored
    async def mine_jargon(self, group_id: str) -> None:
        """Run one jargon mining iteration for a group."""
        try:
            if not self._config.enable_jargon_learning:
                logger.debug("[JargonMining] Jargon learning disabled, skip")
                return

            if not self._jargon_miner_manager:
                logger.debug("[JargonMining] JargonMinerManager not initialised, skip")
                return

            jargon_miner = self._jargon_miner_manager.get_or_create_miner(group_id)

            stats = await self._message_collector.get_statistics(group_id)
            recent_message_count = stats.get("raw_messages", 0)

            if not jargon_miner.should_trigger(recent_message_count):
                logger.debug(
                    f"[JargonMining] Group {group_id} trigger conditions not met"
                )
                return

            recent_messages = await self._db_manager.get_recent_raw_messages(
                group_id, limit=30
            )
            recent_messages = filter_learning_messages(recent_messages)

            if len(recent_messages) < 10:
                logger.debug(
                    f"[JargonMining] Group {group_id} insufficient messages "
                    f"({len(recent_messages)}<10)"
                )
                return

            logger.debug(
                f"[JargonMining] Analysing {len(recent_messages)} messages "
                f"from group {group_id}"
            )

            chat_messages = "\n".join(
                [
                    f"{msg.get('sender_id', 'unknown')}: {msg.get('message', '')}"
                    for msg in recent_messages
                ]
            )

            statistical_candidates = None
            if self._jargon_statistical_filter:
                statistical_candidates = (
                    self._jargon_statistical_filter.get_jargon_candidates(
                        group_id, top_k=20
                    )
                )
                if not statistical_candidates:
                    statistical_candidates = None

            await jargon_miner.run_once(
                chat_messages,
                len(recent_messages),
                statistical_candidates=statistical_candidates,
            )

            logger.debug(f"[JargonMining] Group {group_id} learning complete")

        except Exception as exc:
            logger.error(
                f"[JargonMining] Background task failed (group={group_id}): {exc}",
                exc_info=True,
            )
