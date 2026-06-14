"""
AstrBot 自学习插件 - 智能对话风格学习与人格优化
"""
import os
import asyncio
import time
import shutil
from typing import Dict, Optional
from dataclasses import dataclass
from sys import maxsize

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.event.filter import PermissionType
import astrbot.api.star as star
from astrbot.api.star import Context
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .config import DEFAULT_DATA_DIR, PluginConfig
from .core.plugin_lifecycle import PluginLifecycle
from .services.hooks.perf_tracker import PerfTracker
from .services.monitoring.instrumentation import monitored, reset_trace_context
from .services.learning.sample_filter import (
    extract_learning_event_metadata,
    should_ignore_learning_sample,
)
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


def _migrate_legacy_data_dir(astrbot_data_path: str, plugin_data_dir: str) -> None:
    """Copy legacy self_learning_data into plugin_data when the new dir is empty."""
    legacy_candidates = [
        os.path.join(astrbot_data_path, "self_learning_data"),
        os.path.abspath(os.path.join(".", "data", "self_learning_data")),
    ]
    target = os.path.abspath(plugin_data_dir)
    if os.path.isdir(target) and os.listdir(target):
        return

    for legacy_dir in legacy_candidates:
        legacy = os.path.abspath(legacy_dir)
        if legacy == target or not os.path.isdir(legacy):
            continue
        try:
            os.makedirs(target, exist_ok=True)
            shutil.copytree(legacy, target, dirs_exist_ok=True)
            logger.info(f"已迁移旧版自学习数据目录: {legacy} -> {target}")
            return
        except Exception as exc:
            logger.warning(f"迁移旧版自学习数据目录失败 ({legacy} -> {target}): {exc}")


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
        self.remember_service = None
        self.feature_delegation = None
        self.qq_filter = None
        self.plugin_config = None
        self.page_api = None
        self._message_capture_diag_counts: dict[str, int] = {}
        self._message_capture_diag_last: dict[str, float] = {}

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
                _migrate_legacy_data_dir(astrbot_data_path, plugin_data_dir)

            logger.info(f"最终插件数据目录: {plugin_data_dir}")
            config_file = os.path.join(plugin_data_dir, FileNames.CONFIG_FILE)
            self.plugin_config = PluginConfig.create_from_runtime_sources(
                self.config,
                data_dir=plugin_data_dir,
                config_file=config_file,
            )

            logger.info(f"[插件初始化] Provider配置已加载：")
            logger.info(f" - filter_provider_id: {self.plugin_config.filter_provider_id}")
            logger.info(f" - refine_provider_id: {self.plugin_config.refine_provider_id}")
            logger.info(f" - reinforce_provider_id: {self.plugin_config.reinforce_provider_id}")

        except Exception as e:
            logger.error(f"初始化插件配置失败: {e}")
            default_data_dir = os.path.abspath(DEFAULT_DATA_DIR)
            logger.warning(f"使用默认数据目录: {default_data_dir}")
            config_file = os.path.join(default_data_dir, FileNames.CONFIG_FILE)
            self.plugin_config = PluginConfig.create_from_runtime_sources(
                self.config,
                data_dir=default_data_dir,
                config_file=config_file,
            )

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
        self._shutting_down = False

        # ------ 委托生命周期编排 ------
        # 若 bootstrap() 抛出异常则让其向上传播，
        # AstrBot 的 star_manager 会将插件标记为加载失败并记录到 failed_plugin_dict，
        # 用户可在面板查看失败原因并尝试重载。
        self._lifecycle = PluginLifecycle(self)
        self._lifecycle.bootstrap(
            self.plugin_config, self.context, self.group_id_to_unified_origin
        )
        self._register_official_page_api_if_available()

        logger.info(StatusMessages.PLUGIN_INITIALIZED)

    # 生命周期

    def _register_official_page_api_if_available(self) -> None:
        """Register AstrBot embedded Plugin Page APIs on supported versions."""
        if not hasattr(self.context, "register_web_api"):
            return

        try:
            from .core.page_api import PluginPageApi
        except Exception as exc:
            logger.warning(f"官方插件页面 API 不可用，已跳过注册: {exc}")
            return

        try:
            self.page_api = PluginPageApi(self)
            self.page_api.register_routes()
            logger.info("官方插件页面 API 已注册: /plugin-page/astrbot_plugin_self_learning/dashboard")
        except Exception as exc:
            self.page_api = None
            logger.warning(f"官方插件页面 API 注册失败，已跳过: {exc}", exc_info=True)

    async def initialize(self):
        """AstrBot 在完成 handler 绑定后调用此方法"""
        await self._lifecycle.on_load()

    async def terminate(self):
        """插件卸载时的清理工作"""
        await self._lifecycle.shutdown()

    # 消息监听

    def _log_message_capture_diag(
        self,
        reason: str,
        event: Optional[AstrMessageEvent] = None,
        message_text: Optional[str] = None,
        *,
        level: str = "debug",
    ) -> None:
        """低频输出消息采集诊断，避免线上刷屏。"""
        now = time.monotonic()
        count = self._message_capture_diag_counts.get(reason, 0) + 1
        last = self._message_capture_diag_last.get(reason, 0.0)
        self._message_capture_diag_counts[reason] = count

        if count > 3 and now - last < 60:
            return

        self._message_capture_diag_last[reason] = now

        platform = "unknown"
        group_id = "unknown"
        sender_id = "unknown"
        message_type = "unknown"
        if event:
            for name, getter in (
                ("platform", event.get_platform_name),
                ("group_id", event.get_group_id),
                ("sender_id", event.get_sender_id),
                ("message_type", event.get_message_type),
            ):
                try:
                    value = getter()
                except Exception:
                    value = "error"
                if name == "platform":
                    platform = value
                elif name == "group_id":
                    group_id = value
                elif name == "sender_id":
                    sender_id = value
                elif name == "message_type":
                    message_type = value

        preview = (message_text or "").replace("\n", " ")[:60]
        msg = (
            f"[消息采集] {reason} count={count}, platform={platform}, "
            f"type={message_type}, group={group_id}, sender={sender_id}, preview={preview!r}"
        )

        if level == "info" or count <= 3:
            logger.info(msg)
        else:
            logger.debug(msg)

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL, priority=maxsize - 20)
    @monitored
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，收集用户对话数据（非阻塞优化版）"""
        reset_trace_context()
        try:
            if self._shutting_down:
                self._log_message_capture_diag("skip:shutting_down", event)
                return

            db = getattr(self, 'db_manager', None)
            if not db:
                self._log_message_capture_diag("skip:db_manager_missing", event, level="info")
                return
            db_ready = getattr(db, "is_ready", None)
            if db_ready is not None:
                if not db_ready:
                    self._log_message_capture_diag("skip:db_not_ready", event, level="info")
                    return
            elif not getattr(db, "engine", None):
                self._log_message_capture_diag("skip:db_engine_not_ready", event, level="info")
                return

            message_text = event.get_message_str()
            if not message_text or len(message_text.strip()) == 0:
                self._log_message_capture_diag("skip:empty_message", event, message_text)
                return

            group_id = event.get_group_id() or event.get_sender_id()
            sender_id = event.get_sender_id()
            event_metadata = extract_learning_event_metadata(event)
            if should_ignore_learning_sample(
                message_text,
                sender_id=sender_id,
                **event_metadata,
            ):
                logger.debug(f"检测到指令或系统模板消息，跳过学习数据收集: {message_text[:80]}")
                self._log_message_capture_diag("skip:system_or_command_sample", event, message_text)
                return
            self._log_message_capture_diag("accepted:event_received", event, message_text)

            # 好感度处理（后台，仅 at/唤醒消息）
            pipeline = getattr(self, '_pipeline', None)
            if (
                event.is_at_or_wake_command
                and self.plugin_config
                and self.plugin_config.enable_affection_system
                and pipeline
            ):
                self._track_task(asyncio.create_task(
                    pipeline.process_affection(group_id, sender_id, message_text)
                ))

            if not self.plugin_config or not self.plugin_config.enable_message_capture:
                self._log_message_capture_diag("skip:capture_disabled", event, message_text, level="info")
                return

            # 命令过滤
            cmd_filter = getattr(self, '_command_filter', None)
            if cmd_filter and cmd_filter.is_astrbot_command(event):
                logger.debug(f"检测到AstrBot命令，跳过学习数据收集: {message_text}")
                self._log_message_capture_diag("skip:command_message", event, message_text)
                return

            qq_filter = getattr(self, 'qq_filter', None)
            if qq_filter and not qq_filter.should_collect_message(sender_id, group_id):
                self._log_message_capture_diag("skip:target_filter", event, message_text, level="info")
                return

            if not pipeline:
                self._log_message_capture_diag("skip:pipeline_missing", event, message_text, level="info")
                return

            # 后台学习流水线
            self._track_task(asyncio.create_task(
                self._process_learning_message(group_id, sender_id, message_text, event)
            ))

            self._log_message_capture_diag("queued:learning_pipeline", event, message_text)

        except Exception as e:
            logger.error(StatusMessages.MESSAGE_COLLECTION_ERROR.format(error=e), exc_info=True)

    @monitored
    async def _process_learning_message(
        self,
        group_id: str,
        sender_id: str,
        message_text: str,
        event: AstrMessageEvent,
    ) -> None:
        pipeline = getattr(self, '_pipeline', None)
        if not pipeline:
            self._log_message_capture_diag("skip:pipeline_missing_at_task", event, message_text, level="info")
            return

        collected = await pipeline.process_learning(group_id, sender_id, message_text, event)
        if collected:
            self.learning_stats.total_messages_collected += 1
            if self.plugin_config:
                self.plugin_config.total_messages_collected = self.learning_stats.total_messages_collected
            self._log_message_capture_diag("saved:raw_message", event, message_text, level="info")
        else:
            self._log_message_capture_diag("fail:raw_message_not_saved", event, message_text, level="info")

    def _track_task(self, task: asyncio.Task) -> None:
        """Register a fire-and-forget task for cancellation during shutdown."""
        bg = getattr(self, 'background_tasks', None)
        if bg is not None:
            bg.add(task)
            task.add_done_callback(bg.discard)

    # LLM Hook

    @filter.on_llm_request()
    @monitored
    async def inject_diversity_to_llm_request(self, event: AstrMessageEvent, req=None):
        """LLM Hook — inject diversity, social context, V2, jargon into request."""
        reset_trace_context()
        handler = getattr(self, '_hook_handler', None)
        if handler:
            await handler.handle(event, req)

    # Bot 出站消息捕获

    @filter.after_message_sent()
    @monitored
    async def on_bot_message_sent(self, event: AstrMessageEvent):
        """捕获 Bot 发送的消息并存入数据库，用于 fewshot 对话对提取。"""
        reset_trace_context()
        try:
            if self._shutting_down:
                return
            if not self.plugin_config or not self.plugin_config.enable_message_capture:
                return
            db = getattr(self, 'db_manager', None)
            if not db:
                return
            db_ready = getattr(db, "is_ready", None)
            if db_ready is not None:
                if not db_ready:
                    return
            elif not getattr(db, "engine", None):
                return
            result = event.get_result()
            if not result or not result.chain:
                return
            from astrbot.core.message.components import Plain
            text_parts = []
            for comp in result.chain:
                if isinstance(comp, Plain):
                    text_parts.append(comp.text)
            bot_text = "".join(text_parts).strip()
            if not bot_text:
                return
            if should_ignore_learning_sample(bot_text, sender_id="bot", is_bot=True):
                logger.debug(f"检测到Bot固定输出，跳过学习样本保存: {bot_text[:80]}")
                return
            group_id = event.get_group_id() or event.get_sender_id()
            await db.save_bot_message(
                group_id=group_id,
                message=bot_text,
            )
        except Exception as e:
            logger.warning(f"保存Bot出站消息失败: {e}", exc_info=True)

    # 命令处理器（薄委托）

    @filter.command("learning_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def learning_status_command(self, event: AstrMessageEvent):
        """查看学习状态"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.learning_status(event):
            yield result

    @filter.command("start_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def start_learning_command(self, event: AstrMessageEvent):
        """手动启动学习"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.start_learning(event):
            yield result

    @filter.command("stop_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def stop_learning_command(self, event: AstrMessageEvent):
        """停止学习"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.stop_learning(event):
            yield result

    @filter.command("force_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def force_learning_command(self, event: AstrMessageEvent):
        """强制执行一次学习周期"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.force_learning(event):
            yield result
    @filter.command("remember")
    @filter.permission_type(PermissionType.ADMIN)
    async def remember_command(self, event: AstrMessageEvent):
        """手动记住引用对话及上下文，并链入表达方式和对话示例"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.remember(event):
            yield result

    @filter.command("remember")
    @filter.permission_type(PermissionType.ADMIN)
    async def remember_command(self, event: AstrMessageEvent):
        """手动记住引用对话及上下文，并链入表达方式和对话示例"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.remember(event):
            yield result

    @filter.command("affection_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def affection_status_command(self, event: AstrMessageEvent):
        """查看好感度状态"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.affection_status(event):
            yield result

    @filter.command("set_mood")
    @filter.permission_type(PermissionType.ADMIN)
    async def set_mood_command(self, event: AstrMessageEvent):
        """手动设置bot情绪"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.set_mood(event):
            yield result
