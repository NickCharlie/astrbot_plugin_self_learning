"""插件命令业务逻辑实现 — 6 个 admin 命令的处理体"""
import time
from typing import Any, AsyncGenerator

from astrbot.api import logger

from ...statics.messages import CommandMessages, LogMessages


class PluginCommandHandlers:
    """6 个 @filter.command 命令的业务逻辑（从 main.py 提取）"""

    def __init__(
        self,
        plugin_config: Any,
        service_factory: Any,
        message_collector: Any,
        persona_manager: Any,
        progressive_learning: Any,
        affection_manager: Any,
        temporary_persona_updater: Any,
        db_manager: Any,
        llm_adapter: Any,
    ):
        self._config = plugin_config
        self._service_factory = service_factory
        self._message_collector = message_collector
        self._persona_manager = persona_manager
        self._progressive_learning = progressive_learning
        self._affection_manager = affection_manager
        self._temporary_persona_updater = temporary_persona_updater
        self._db_manager = db_manager
        self._llm_adapter = llm_adapter
        self._force_learning_in_progress: set = set()

    # ------------------------------------------------------------------
    # learning_status
    # ------------------------------------------------------------------

    async def learning_status(self, event: Any) -> AsyncGenerator:
        """查看学习状态"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()

            collector_stats = await self._message_collector.get_statistics(group_id)
            if collector_stats is None:
                collector_stats = {
                    "total_messages": 0,
                    "filtered_messages": 0,
                    "raw_messages": 0,
                    "unprocessed_messages": 0,
                }

            current_persona_info = await self._persona_manager.get_current_persona(group_id)
            current_persona_name = CommandMessages.STATUS_UNKNOWN
            if current_persona_info and isinstance(current_persona_info, dict):
                current_persona_name = current_persona_info.get("name", CommandMessages.STATUS_UNKNOWN)

            learning_status = await self._progressive_learning.get_learning_status()
            if learning_status is None:
                learning_status = {
                    "learning_active": False,
                    "current_session": None,
                    "total_sessions": 0,
                }

            status_info = CommandMessages.STATUS_REPORT_HEADER.format(group_id=group_id)

            persona_update_mode = (
                "PersonaManager模式"
                if self._config.use_persona_manager_updates
                else "传统文件模式"
            )
            status_info += CommandMessages.STATUS_BASIC_CONFIG.format(
                message_capture=(
                    CommandMessages.STATUS_ENABLED
                    if self._config.enable_message_capture
                    else CommandMessages.STATUS_DISABLED
                ),
                auto_learning=(
                    CommandMessages.STATUS_ENABLED
                    if self._config.enable_auto_learning
                    else CommandMessages.STATUS_DISABLED
                ),
                realtime_learning=(
                    CommandMessages.STATUS_ENABLED
                    if self._config.enable_realtime_learning
                    else CommandMessages.STATUS_DISABLED
                ),
                web_interface=(
                    CommandMessages.STATUS_ENABLED
                    if self._config.enable_web_interface
                    else CommandMessages.STATUS_DISABLED
                ),
            )

            status_info += f"\n\n📊 人格更新配置:\n"
            status_info += f"• 更新方式: {persona_update_mode}\n"
            if self._config.use_persona_manager_updates:
                persona_manager_updater = self._service_factory.create_persona_manager_updater()
                pm_status = "✅ 可用" if persona_manager_updater.is_available() else "❌ 不可用"
                status_info += f"• PersonaManager状态: {pm_status}\n"
                status_info += f"• 自动应用更新: {'启用' if self._config.auto_apply_persona_updates else '禁用'}\n"
            status_info += f"• 更新前备份: {'启用' if self._config.persona_update_backup_enabled else '禁用'}\n"

            status_info += CommandMessages.STATUS_CAPTURE_SETTINGS.format(
                target_qq=(
                    self._config.target_qq_list
                    if self._config.target_qq_list
                    else CommandMessages.STATUS_ALL_USERS
                ),
                current_persona=current_persona_name,
            )

            if self._llm_adapter:
                provider_info = self._llm_adapter.get_provider_info()
                status_info += CommandMessages.STATUS_MODEL_CONFIG.format(
                    filter_model=provider_info.get("filter", "未配置"),
                    refine_model=provider_info.get("refine", "未配置"),
                )
            else:
                status_info += CommandMessages.STATUS_MODEL_CONFIG.format(
                    filter_model="未配置框架Provider",
                    refine_model="未配置框架Provider",
                )

            current_session = learning_status.get("current_session") or {}
            status_info += CommandMessages.STATUS_LEARNING_STATS.format(
                total_messages=collector_stats.get("total_messages", 0),
                filtered_messages=collector_stats.get("filtered_messages", 0),
                style_updates=current_session.get("style_updates", 0),
                last_learning_time=current_session.get(
                    "end_time", CommandMessages.STATUS_NEVER_EXECUTED
                ),
            )

            status_info += CommandMessages.STATUS_STORAGE_STATS.format(
                raw_messages=collector_stats.get("raw_messages", 0),
                unprocessed_messages=collector_stats.get("unprocessed_messages", 0),
                filtered_messages=collector_stats.get("filtered_messages", 0),
            )

            scheduler_status = (
                CommandMessages.STATUS_RUNNING
                if learning_status.get("learning_active")
                else CommandMessages.STATUS_STOPPED
            )
            status_info += "\n\n" + CommandMessages.STATUS_SCHEDULER.format(
                status=scheduler_status
            )

            yield event.plain_result(status_info.strip())

        except Exception as e:
            logger.error(
                CommandMessages.ERROR_GET_LEARNING_STATUS.format(error=e),
                exc_info=True,
            )
            yield event.plain_result(
                CommandMessages.STATUS_QUERY_FAILED.format(error=str(e))
            )

    # ------------------------------------------------------------------
    # start_learning
    # ------------------------------------------------------------------

    async def start_learning(self, event: Any) -> AsyncGenerator:
        """手动启动学习"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()

            stats = await self._message_collector.get_statistics(group_id)
            unprocessed_count = stats.get("unprocessed_messages", 0)

            if unprocessed_count < self._config.min_messages_for_learning:
                yield event.plain_result(
                    f"❌ 未处理消息数量不足"
                    f"（{unprocessed_count}/{self._config.min_messages_for_learning}），"
                    f"无法开始学习"
                )
                return

            yield event.plain_result(
                f"🔄 开始执行学习批次，处理 {unprocessed_count} 条未处理消息..."
            )

            try:
                await self._progressive_learning._execute_learning_batch(group_id)
                yield event.plain_result("✅ 学习批次执行完成")
            except Exception as batch_error:
                yield event.plain_result(f"❌ 学习批次执行失败: {str(batch_error)}")

        except Exception as e:
            logger.error(
                CommandMessages.ERROR_START_LEARNING.format(error=e), exc_info=True
            )
            yield event.plain_result(
                CommandMessages.STARTUP_FAILED.format(error=str(e))
            )

    # ------------------------------------------------------------------
    # stop_learning
    # ------------------------------------------------------------------

    async def stop_learning(self, event: Any) -> AsyncGenerator:
        """停止学习"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            await self._progressive_learning.stop_learning()
            yield event.plain_result(
                CommandMessages.LEARNING_STOPPED.format(group_id=group_id)
            )
        except Exception as e:
            logger.error(
                CommandMessages.ERROR_STOP_LEARNING.format(error=e), exc_info=True
            )
            yield event.plain_result(
                CommandMessages.STOP_FAILED.format(error=str(e))
            )

    # ------------------------------------------------------------------
    # force_learning
    # ------------------------------------------------------------------

    async def force_learning(self, event: Any) -> AsyncGenerator:
        """强制执行一次学习周期"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            yield event.plain_result(
                CommandMessages.FORCE_LEARNING_START.format(group_id=group_id)
            )

            if group_id in self._force_learning_in_progress:
                yield event.plain_result(
                    f"❌ 群组 {group_id} 的强制学习正在进行中，请等待完成"
                )
                return

            self._force_learning_in_progress.add(group_id)
            try:
                await self._progressive_learning._execute_learning_batch(group_id)
                yield event.plain_result(
                    CommandMessages.FORCE_LEARNING_COMPLETE.format(group_id=group_id)
                )
            finally:
                self._force_learning_in_progress.discard(group_id)

        except Exception as e:
            logger.error(
                CommandMessages.ERROR_FORCE_LEARNING.format(error=e), exc_info=True
            )
            yield event.plain_result(
                CommandMessages.ERROR_FORCE_LEARNING.format(error=str(e))
            )

    # ------------------------------------------------------------------
    # affection_status
    # ------------------------------------------------------------------

    async def affection_status(self, event: Any) -> AsyncGenerator:
        """查看好感度状态"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            user_id = event.get_sender_id()

            if not self._config.enable_affection_system:
                yield event.plain_result(CommandMessages.AFFECTION_DISABLED)
                return

            affection_status = await self._affection_manager.get_affection_status(group_id)

            current_mood = None
            if self._config.enable_startup_random_mood:
                current_mood = await self._affection_manager.ensure_mood_for_group(group_id)
            else:
                current_mood = await self._affection_manager.get_current_mood(group_id)

            user_affection = await self._db_manager.get_user_affection(group_id, user_id)
            user_level = user_affection["affection_level"] if user_affection else 0

            status_info = CommandMessages.AFFECTION_STATUS_HEADER.format(group_id=group_id)
            status_info += "\n\n" + CommandMessages.AFFECTION_USER_LEVEL.format(
                user_level=user_level, max_affection=self._config.max_user_affection
            )
            status_info += "\n" + CommandMessages.AFFECTION_TOTAL_STATUS.format(
                total_affection=affection_status["total_affection"],
                max_total_affection=affection_status["max_total_affection"],
            )
            status_info += "\n" + CommandMessages.AFFECTION_USER_COUNT.format(
                user_count=affection_status["user_count"]
            )
            status_info += "\n\n" + CommandMessages.AFFECTION_CURRENT_MOOD

            if current_mood:
                mood_info = current_mood
                status_info += "\n" + CommandMessages.AFFECTION_MOOD_TYPE.format(
                    mood_type=mood_info.mood_type.value
                )
                status_info += "\n" + CommandMessages.AFFECTION_MOOD_INTENSITY.format(
                    intensity=mood_info.intensity
                )
                status_info += "\n" + CommandMessages.AFFECTION_MOOD_DESCRIPTION.format(
                    description=mood_info.description
                )
            else:
                status_info += "\n" + CommandMessages.AFFECTION_NO_MOOD

            if affection_status["top_users"]:
                status_info += "\n\n" + CommandMessages.AFFECTION_TOP_USERS
                for i, user in enumerate(affection_status["top_users"][:3], 1):
                    status_info += "\n" + CommandMessages.AFFECTION_USER_RANK.format(
                        rank=i,
                        user_id=user["user_id"],
                        affection_level=user["affection_level"],
                    )

            yield event.plain_result(status_info)

        except Exception as e:
            logger.error(
                CommandMessages.ERROR_GET_AFFECTION_STATUS.format(error=e),
                exc_info=True,
            )
            yield event.plain_result(
                CommandMessages.ERROR_GET_AFFECTION_STATUS.format(error=str(e))
            )

    # ------------------------------------------------------------------
    # set_mood
    # ------------------------------------------------------------------

    async def set_mood(self, event: Any) -> AsyncGenerator:
        """手动设置 bot 情绪（通过增量人格更新）"""
        try:
            if not self._config.enable_affection_system:
                yield event.plain_result(CommandMessages.AFFECTION_DISABLED)
                return

            args = event.get_message_str().split()[1:]
            if len(args) < 1:
                yield event.plain_result(
                    "使用方法：/set_mood <mood_type>\n"
                    "可用情绪: happy, sad, excited, calm, angry, "
                    "anxious, playful, serious, nostalgic, curious"
                )
                return

            group_id = event.get_group_id() or event.get_sender_id()
            mood_type = args[0].lower()

            valid_moods = {
                "happy": "心情很好，说话比较活泼开朗，容易表达正面情感",
                "sad": "心情有些低落，说话比较温和，需要更多的理解和安慰",
                "excited": "很兴奋，说话比较有活力，对很多事情都很感兴趣",
                "calm": "心情平静，说话比较稳重，给人安全感",
                "angry": "心情不太好，说话可能比较直接，不太有耐心",
                "anxious": "有些紧张不安，说话可能比较谨慎，需要更多确认",
                "playful": "心情很调皮，喜欢开玩笑，说话比较幽默风趣",
                "serious": "比较严肃认真，说话简洁直接，专注于重要的事情",
                "nostalgic": "有些怀旧情绪，说话带有回忆色彩，比较感性",
                "curious": "对很多事情都很好奇，喜欢提问和探索新事物",
            }

            if mood_type not in valid_moods:
                yield event.plain_result(
                    f"❌ 无效的情绪类型。支持的情绪: {', '.join(valid_moods.keys())}"
                )
                return

            mood_description = valid_moods[mood_type]

            persona_success = (
                await self._temporary_persona_updater.apply_mood_based_persona_update(
                    group_id, mood_type, mood_description
                )
            )

            # 同时在 affection_manager 中记录情绪状态
            from ...services.state import MoodType, BotMood

            affection_success = False
            try:
                mood_enum = MoodType(mood_type)
                await self._affection_manager.db_manager.save_bot_mood(
                    group_id,
                    mood_type,
                    0.7,
                    mood_description,
                    self._config.mood_persistence_hours or 24,
                )
                mood_obj = BotMood(
                    mood_type=mood_enum,
                    intensity=0.7,
                    description=mood_description,
                    start_time=time.time(),
                    duration_hours=self._config.mood_persistence_hours or 24,
                )
                self._affection_manager.current_moods[group_id] = mood_obj
                affection_success = True
            except Exception as e:
                logger.warning(f"设置 affection_manager 情绪失败: {e}")

            if persona_success:
                status_msg = f"✅ 情绪状态已设置为: {mood_type}\n描述: {mood_description}"
                if not affection_success:
                    status_msg += "\n⚠️ 注意：情绪状态可能无法在状态查询中正确显示"
                yield event.plain_result(status_msg)
            else:
                yield event.plain_result("❌ 设置情绪状态失败")

        except Exception as e:
            logger.error(
                CommandMessages.ERROR_SET_MOOD.format(error=e), exc_info=True
            )
            yield event.plain_result(
                CommandMessages.ERROR_SET_MOOD.format(error=str(e))
            )
