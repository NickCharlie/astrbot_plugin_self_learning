"""Group learning orchestration — smart-start, auto-start, active group discovery.

Manages per-group learning tasks, throttling, and automatic scheduling.
"""

import asyncio
import time
from typing import Any, Dict, List

from astrbot.api import logger


class GroupLearningOrchestrator:
    """Orchestrate learning tasks across chat groups.

    Owns the ``learning_tasks`` mapping and provides methods to smart-start
    learning, discover active groups, and clean up on shutdown.

    Args:
        plugin_config: Plugin configuration object.
        message_collector: Message collector service.
        progressive_learning: Progressive learning service.
        service_factory: Service factory from ``FactoryManager``.
        qq_filter: QQ group filter with whitelist/blacklist support.
        db_manager: Database manager for ORM queries.
    """

    def __init__(
        self,
        plugin_config: Any,
        message_collector: Any,
        progressive_learning: Any,
        qq_filter: Any,
        db_manager: Any,
    ) -> None:
        self._config = plugin_config
        self._message_collector = message_collector
        self._progressive_learning = progressive_learning
        self._qq_filter = qq_filter
        self._db_manager = db_manager

        self.learning_tasks: Dict[str, asyncio.Task] = {}

        # Per-group last-start timestamps (keyed by group_id)
        self._last_learning_start: Dict[str, float] = {}

    # Public API

    async def smart_start_learning_for_group(self, group_id: str) -> None:
        """Smart-start a learning task for *group_id* with frequency throttling."""
        try:
            if group_id in self.learning_tasks:
                return

            current_time = time.time()
            last_start = self._last_learning_start.get(group_id, 0)
            interval_seconds = self._config.learning_interval_hours * 3600

            if current_time - last_start < interval_seconds:
                remaining = interval_seconds - (current_time - last_start)
                logger.debug(
                    f"群组 {group_id} 学习间隔未到，剩余时间: {remaining / 60:.1f}分钟"
                )
                return

            stats = await self._message_collector.get_statistics(group_id)
            if not isinstance(stats, dict):
                logger.warning(
                    f"get_statistics 返回了非字典类型: {type(stats)}, "
                    f"值: {stats}, 跳过学习启动"
                )
                return

            total_messages = self._safe_int(
                stats.get("total_messages", 0), "total_messages"
            )
            if total_messages is None:
                return

            min_messages = self._safe_int(
                self._config.min_messages_for_learning,
                "min_messages_for_learning",
                default=10,
            )

            if total_messages < min_messages:
                logger.debug(
                    f"群组 {group_id} 消息数量未达到学习阈值: "
                    f"{total_messages}/{min_messages}"
                )
                return

            self._last_learning_start[group_id] = current_time

            learning_task = asyncio.create_task(
                self._start_group_learning(group_id)
            )

            def _on_complete(task: asyncio.Task) -> None:
                self.learning_tasks.pop(group_id, None)
                if task.exception():
                    logger.error(
                        f"群组 {group_id} 学习任务异常: {task.exception()}"
                    )
                else:
                    logger.info(f"群组 {group_id} 学习任务完成")

            learning_task.add_done_callback(_on_complete)
            self.learning_tasks[group_id] = learning_task
            logger.info(f"为群组 {group_id} 启动了智能学习任务")

        except Exception as e:
            logger.error(f"智能启动学习失败: {e}")

    async def delayed_auto_start_learning(self) -> None:
        """Auto-start learning for active groups after a startup delay."""
        try:
            await asyncio.sleep(30)
            active_groups = await self.get_active_groups()

            for group_id in active_groups:
                try:
                    await self.smart_start_learning_for_group(group_id)
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"延迟启动群组 {group_id} 学习失败: {e}")

        except Exception as e:
            logger.error(f"延迟自动启动学习失败: {e}")

    async def get_active_groups(self) -> List[str]:
        """Discover active groups using ORM queries with whitelist/blacklist."""
        try:
            if not self._db_manager:
                logger.warning("数据库管理器未初始化，无法获取活跃群组")
                return []

            if hasattr(self._db_manager, "_started") and not self._db_manager._started:
                logger.warning("SQLAlchemy 数据库管理器未启动，无法获取活跃群组")
                return []

            allowed_groups = self._qq_filter.get_allowed_group_ids()
            blocked_groups = self._qq_filter.get_blocked_group_ids()

            if allowed_groups:
                logger.info(f"应用群组白名单过滤，仅查询: {allowed_groups}")
            if blocked_groups:
                logger.info(f"应用群组黑名单过滤，排除: {blocked_groups}")

            async with self._db_manager.get_session() as session:
                from sqlalchemy import select, func
                from ...models.orm import RawMessage

                def _apply_filter(stmt):
                    if allowed_groups:
                        stmt = stmt.where(RawMessage.group_id.in_(allowed_groups))
                    if blocked_groups:
                        stmt = stmt.where(RawMessage.group_id.notin_(blocked_groups))
                    return stmt

                # Progressively widen the search window: 24h → 7d → all-time
                for label, cutoff in (
                    ("24小时", int(time.time() - 86400)),
                    ("7天", int(time.time() - 86400 * 7)),
                    ("全部", None),
                ):
                    base = select(
                        RawMessage.group_id,
                        func.count(RawMessage.id).label("msg_count"),
                    ).where(
                        RawMessage.group_id.isnot(None),
                        RawMessage.group_id != "",
                    )

                    if cutoff is not None:
                        base = base.where(RawMessage.timestamp > cutoff)

                    base = _apply_filter(base)

                    min_msgs = self._config.min_messages_for_learning
                    if label == "7天":
                        min_msgs = max(1, min_msgs // 2)
                    elif label == "全部":
                        min_msgs = 1

                    stmt = (
                        base.group_by(RawMessage.group_id)
                        .having(func.count(RawMessage.id) >= min_msgs)
                        .order_by(func.count(RawMessage.id).desc())
                        .limit(10)
                    )

                    result = await session.execute(stmt)
                    active_groups = [
                        row.group_id for row in result if row.group_id
                    ]

                    if active_groups:
                        logger.info(
                            f"在{label}范围内发现 {len(active_groups)} 个活跃群组: "
                            f"{active_groups}"
                        )
                        return active_groups

                    if cutoff is not None:
                        logger.warning(
                            f"最近{label}内没有活跃群组，扩大搜索范围..."
                        )

                logger.info("未发现任何活跃群组")
                return []

        except Exception as e:
            logger.error(f"获取活跃群组失败: {e}")
            return []

    async def cancel_all(self) -> None:
        """Cancel all running learning tasks (called during shutdown)."""
        _timeout = self._config.task_cancel_timeout

        # Signal all groups to stop first (non-blocking)
        try:
            await asyncio.wait_for(
                self._progressive_learning.stop_learning(),
                timeout=_timeout,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"stop_learning 超时或失败: {e}")

        # Cancel and wait for each task with individual timeouts
        for group_id, task in list(self.learning_tasks.items()):
            try:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=_timeout)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                logger.info(f"群组 {group_id} 学习任务已停止")
            except Exception as e:
                logger.error(f"停止群组 {group_id} 学习任务失败: {e}")
        self.learning_tasks.clear()

    # Internal helpers

    async def _start_group_learning(self, group_id: str) -> None:
        """Start the progressive learning session for a single group."""
        try:
            success = await self._progressive_learning.start_learning(group_id)
            if success:
                logger.info(f"群组 {group_id} 学习任务启动成功")
            else:
                logger.warning(f"群组 {group_id} 学习任务启动失败")
        except Exception as e:
            logger.error(f"群组 {group_id} 学习任务启动异常: {e}")

    @staticmethod
    def _safe_int(
        value: Any, name: str, *, default: int | None = None
    ) -> int | None:
        """Safely convert *value* to ``int`` with detailed logging."""
        try:
            if isinstance(value, str) and not value.replace("-", "").isdigit():
                if default is not None:
                    logger.warning(
                        f"{name} 是非数字字符串: '{value}', 使用默认值{default}"
                    )
                    return default
                logger.warning(f"{name} 是非数字字符串: '{value}', 跳过")
                return None
            return int(value) if value else 0
        except (ValueError, TypeError) as e:
            if default is not None:
                logger.warning(
                    f"{name} 转换失败: 原始值={value}, 错误={e}, "
                    f"使用默认值{default}"
                )
                return default
            logger.warning(
                f"{name} 转换失败: 原始值={value}, 类型={type(value)}, 错误={e}"
            )
            return None
