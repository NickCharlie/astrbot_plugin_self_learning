"""
AstrBot 自学习插件 - 智能对话风格学习与人格优化
"""
import os
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.event.filter import PermissionType
import astrbot.api.star as star
from astrbot.api.star import Context
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .config import PluginConfig
from .core.plugin_lifecycle import PluginLifecycle
from .services.hooks.perf_tracker import PerfTracker
from .statics.messages import StatusMessages, FileNames


def _safe(value: object) -> str:
    """将任意值转为对 GBK 控制台安全的字符串。

    Windows 中文版默认控制台编码为 GBK，logger 输出包含 emoji 或
    生僻 Unicode 时会抛出 UnicodeEncodeError。此函数将不可编码
    字符替换为 ``?``，保证日志不会因编码问题而中断。
    """
    try:
        s = str(value)
        s.encode("gbk")
        return s
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s.encode("gbk", errors="replace").decode("gbk")


@dataclass
class LearningStats:
    """学习统计信息"""
    total_messages_collected: int = 0
    filtered_messages: int = 0
    style_updates: int = 0
    persona_updates: int = 0
    last_learning_time: Optional[str] = None
    last_persona_update: Optional[str] = None


class SelfLearningPlugin(star.Star):
    """AstrBot 自学习插件 - 智能学习用户对话风格并优化人格设置"""

    def __init__(self, context: Context, config: AstrBotConfig = None) -> None:
        super().__init__(context)
        self.context = context
        self.config = config or {}

        # Pre-initialize handler-accessed attributes so they exist even if
        # bootstrap() fails.  Without this, a bootstrap exception propagates
        # through __init__, AstrBot's star_manager skips functools.partial
        # handler binding, and every handler call crashes with
        # "missing 1 required positional argument: 'event'".
        self.db_manager = None
        self._pipeline = None
        self._hook_handler = None
        self._command_handlers = None
        self._command_filter = None
        self.qq_filter = None
        self.plugin_config = None

        # ------ 插件配置加载 ------
        try:
            astrbot_data_path = get_astrbot_data_path()
            if astrbot_data_path is None:
                astrbot_data_path = os.path.join(os.path.dirname(__file__), "data")
                logger.warning("无法获取 AstrBot 数据路径，使用插件目录下的 data 目录")

            storage_settings = self.config.get('Storage_Settings', {}) if self.config else {}
            user_data_dir = storage_settings.get('data_dir')

            if user_data_dir:
                logger.info(f"使用用户自定义数据路径 (从Storage_Settings.data_dir): {user_data_dir}")
                plugin_data_dir = user_data_dir
                if not os.path.isabs(plugin_data_dir):
                    plugin_data_dir = os.path.abspath(plugin_data_dir)
            else:
                plugin_data_dir = os.path.join(
                    astrbot_data_path, "plugin_data", "astrbot_plugin_self_learning"
                )
                logger.info(f"使用默认数据路径: {plugin_data_dir}")

            logger.info(f"最终插件数据目录: {plugin_data_dir}")
            self.plugin_config = PluginConfig.create_from_config(self.config, data_dir=plugin_data_dir)

            logger.info(f"[插件初始化] Provider配置已加载：")
            logger.info(f" - filter_provider_id: {self.plugin_config.filter_provider_id}")
            logger.info(f" - refine_provider_id: {self.plugin_config.refine_provider_id}")
            logger.info(f" - reinforce_provider_id: {self.plugin_config.reinforce_provider_id}")

        except Exception as e:
            logger.error(f"初始化插件配置失败: {e}")
            default_data_dir = os.path.join(os.path.dirname(__file__), "data")
            logger.warning(f"使用默认数据目录: {default_data_dir}")
            self.plugin_config = PluginConfig.create_from_config(self.config, data_dir=default_data_dir)

        os.makedirs(self.plugin_config.data_dir, exist_ok=True)

        if not self.plugin_config.messages_db_path:
            self.plugin_config.messages_db_path = os.path.join(
                self.plugin_config.data_dir, FileNames.MESSAGES_DB_FILE
            )
        if not self.plugin_config.learning_log_path:
            self.plugin_config.learning_log_path = os.path.join(
                self.plugin_config.data_dir, FileNames.LEARNING_LOG_FILE
            )

        # ------ 运行时状态 ------
        self.learning_stats = LearningStats()
        self.message_dedup_cache: dict = {}
        self.max_cache_size = 1000
        self.group_id_to_unified_origin: Dict[str, str] = {}
        self.update_system_prompt_callback = None
        self._perf_tracker = PerfTracker(maxlen=200)

        # ------ 委托生命周期编排 ------
        # Wrapped in try/except: if bootstrap() raises, AstrBot's
        # star_manager catches the exception at the outer BaseException
        # handler, which skips functools.partial handler binding entirely.
        # The unbound handlers then remain in star_handlers_registry and
        # get invoked without `self`, causing the "missing argument" crash.
        self._lifecycle = PluginLifecycle(self)
        try:
            self._lifecycle.bootstrap(
                self.plugin_config, self.context, self.group_id_to_unified_origin
            )
        except Exception as e:
            logger.error(
                f"插件服务编排失败，部分功能将不可用: {e}", exc_info=True
            )

        logger.info(StatusMessages.PLUGIN_INITIALIZED)

    # 生命周期

    async def initialize(self):
        """AstrBot 在完成 handler 绑定后调用此方法"""
        await self._lifecycle.on_load()

    async def terminate(self):
        """插件卸载时的清理工作"""
        await self._lifecycle.shutdown()

    # 消息监听

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，收集用户对话数据（非阻塞优化版）"""
        try:
            db = getattr(self, 'db_manager', None)
            if not db or not db.engine:
                return

            message_text = event.get_message_str()
            if not message_text or len(message_text.strip()) == 0:
                return

            group_id = event.get_group_id() or event.get_sender_id()
            sender_id = event.get_sender_id()

            # 好感度处理（后台，仅 at/唤醒消息）
            pipeline = getattr(self, '_pipeline', None)
            if (
                event.is_at_or_wake_command
                and self.plugin_config
                and self.plugin_config.enable_affection_system
                and pipeline
            ):
                asyncio.create_task(
                    pipeline.process_affection(group_id, sender_id, message_text)
                )

            if not self.plugin_config or not self.plugin_config.enable_message_capture:
                return

            # 命令过滤
            cmd_filter = getattr(self, '_command_filter', None)
            if cmd_filter and cmd_filter.is_astrbot_command(event):
                logger.debug(f"检测到AstrBot命令，跳过学习数据收集: {message_text}")
                return

            qq_filter = getattr(self, 'qq_filter', None)
            if qq_filter and not qq_filter.should_collect_message(sender_id, group_id):
                return

            if not pipeline:
                return

            # 后台学习流水线
            asyncio.create_task(
                pipeline.process_learning(group_id, sender_id, message_text, event)
            )

            self.learning_stats.total_messages_collected += 1
            self.plugin_config.total_messages_collected = self.learning_stats.total_messages_collected

        except Exception as e:
            logger.error(StatusMessages.MESSAGE_COLLECTION_ERROR.format(error=e), exc_info=True)

    # LLM Hook

    @filter.on_llm_request()
    async def inject_diversity_to_llm_request(self, event: AstrMessageEvent, req=None):
        """LLM Hook — inject diversity, social context, V2, jargon into request."""
        handler = getattr(self, '_hook_handler', None)
        if handler:
            await handler.handle(event, req)

    # 命令处理器（薄委托）

    @filter.command("learning_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def learning_status_command(self, event: AstrMessageEvent):
        """查看学习状态"""
        async for result in self._command_handlers.learning_status(event):
            yield result

    @filter.command("start_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def start_learning_command(self, event: AstrMessageEvent):
        """手动启动学习"""
        async for result in self._command_handlers.start_learning(event):
            yield result

    @filter.command("stop_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def stop_learning_command(self, event: AstrMessageEvent):
        """停止学习"""
        async for result in self._command_handlers.stop_learning(event):
            yield result

    @filter.command("force_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def force_learning_command(self, event: AstrMessageEvent):
        """强制执行一次学习周期"""
        async for result in self._command_handlers.force_learning(event):
            yield result

    @filter.command("affection_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def affection_status_command(self, event: AstrMessageEvent):
        """查看好感度状态"""
        async for result in self._command_handlers.affection_status(event):
            yield result

    @filter.command("set_mood")
    @filter.permission_type(PermissionType.ADMIN)
    async def set_mood_command(self, event: AstrMessageEvent):
        """手动设置bot情绪"""
        async for result in self._command_handlers.set_mood(event):
            yield result
