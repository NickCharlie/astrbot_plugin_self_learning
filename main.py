"""
AstrBot 自学习插件 - 智能对话风格学习与人格优化
"""
import os
import asyncio
import time
import shutil
import json
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
from sys import maxsize

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
import astrbot.api.star as star
from astrbot.api.star import Context, StarTools
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .config import DEFAULT_DATA_DIR, PluginConfig, normalize_identifier_list, split_learning_blacklist
from .core.plugin_lifecycle import PluginLifecycle
from .affection_query import add_guidance as add_affection_guidance, query as query_affection_snapshot
from .services.hooks.perf_tracker import PerfTracker
from .services.monitoring.instrumentation import monitored, reset_trace_context
from .services.learning.sample_filter import (
    extract_learning_event_metadata,
    is_learning_blacklisted,
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


def _archive_legacy_config_copy(config_file: str) -> None:
    """Move the old WebUI config copy aside so it cannot be mistaken as active."""
    if not os.path.isfile(config_file):
        return

    archive_path = f"{config_file}.legacy"
    if os.path.exists(archive_path):
        archive_path = f"{config_file}.{int(time.time())}.legacy"

    try:
        os.replace(config_file, archive_path)
        logger.info(f"已归档旧版 WebUI 配置副本: {archive_path}")
    except OSError as exc:
        logger.warning(f"归档旧版 WebUI 配置副本失败，将继续忽略该文件: {exc}")


def _default_plugin_data_dir(astrbot_data_path: str) -> str:
    try:
        data_dir = StarTools.get_data_dir()
        if isinstance(data_dir, Path):
            return os.fspath(data_dir)
        if data_dir:
            return os.fspath(data_dir)
    except Exception as exc:
        logger.warning(f"StarTools.get_data_dir() 不可用，回退到 AstrBot 数据目录: {exc}")

    return os.path.join(
        astrbot_data_path,
        "plugin_data",
        "astrbot_plugin_self_learning",
    )


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
                plugin_data_dir = _default_plugin_data_dir(astrbot_data_path)
                logger.info(f"使用默认数据路径: {plugin_data_dir}")
                _migrate_legacy_data_dir(astrbot_data_path, plugin_data_dir)

            logger.info(f"最终插件数据目录: {plugin_data_dir}")
            config_file = os.path.join(plugin_data_dir, FileNames.CONFIG_FILE)
            self.plugin_config = PluginConfig.create_from_runtime_sources(
                self.config,
                data_dir=plugin_data_dir,
                config_file=config_file,
                astrbot_config_file=getattr(self.config, "config_path", None),
            )
            _archive_legacy_config_copy(config_file)

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
                astrbot_config_file=getattr(self.config, "config_path", None),
            )
            _archive_legacy_config_copy(config_file)

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
        self._trigger_dashboard_autobuild()

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
            from .utils.framework_compat import plugin_page_hash_url

            logger.info(
                "官方插件页面 API 已注册: "
                f"{plugin_page_hash_url('astrbot_plugin_self_learning', 'dashboard')}"
            )
        except Exception as exc:
            self.page_api = None
            logger.warning(f"官方插件页面 API 注册失败，已跳过: {exc}", exc_info=True)

    def _trigger_dashboard_autobuild(self) -> None:
        """后台检测并自动构建 Dashboard 前端（仅在产物缺失时触发）。

        - 产物已就绪则直接跳过（生产环境随仓库分发，开箱即用）。
        - 缺失时以 ``asyncio.create_task`` 后台执行，绝不阻塞插件启动，
          任何异常仅记录日志，不影响插件加载。
        """
        try:
            plugin_root = os.path.dirname(os.path.abspath(__file__))
            from .webui.frontend_builder import (
                dashboard_artifact_exists,
                ensure_dashboard_built,
            )

            if dashboard_artifact_exists(plugin_root):
                return

            loop = asyncio.get_running_loop()
            _t = loop.create_task(ensure_dashboard_built(plugin_root))
            bg = getattr(self, "background_tasks", None)
            if bg is not None:
                bg.add(_t)
                _t.add_done_callback(bg.discard)
        except Exception as exc:
            logger.warning(
                f"[WebUI] Dashboard 自动构建触发失败（不影响插件运行）：{exc}",
                exc_info=True,
            )

    async def initialize(self):
        """AstrBot 在完成 handler 绑定后调用此方法"""
        await self._lifecycle.on_load()

    async def terminate(self):
        """插件卸载时的清理工作"""
        await self._lifecycle.shutdown()

    # 消息监听

    def _queue_style_context_capture(self, group_id, sender_id, message_text, event) -> bool:
        """Capture group context or blank boundaries without learning side effects."""
        config = getattr(self, "plugin_config", None)
        pipeline = getattr(self, "_pipeline", None)
        if not config or not config.enable_message_capture or not pipeline or not event.get_group_id():
            return False
        targets = normalize_identifier_list(
            getattr(config, "target_qq_list", []), full_learning_markers=True,
        )
        if targets and all(target.startswith("group_") for target in targets):
            if f"group_{group_id}" not in targets:
                return False
        blocked_senders, blocked_groups = split_learning_blacklist(config.target_blacklist)
        if is_learning_blacklisted(
            sender_id, group_id, blocked_sender_ids=blocked_senders,
            blocked_group_ids=blocked_groups,
        ):
            return False
        self._track_task(asyncio.create_task(
            pipeline.capture_style_context(group_id, sender_id, message_text, event)
        ))
        return True

    def _is_self_message(self, event: AstrMessageEvent, sender_id: Optional[str]) -> bool:
        """入站消息是否由 bot 自身发出。

        issue #284：bot 自身账号默认不进学习数据，不要求用户把 self_id 手填黑名单；
        部分平台会把 bot 自己发的消息再投递为事件，这些样本会污染学习。
        """
        getter = getattr(event, "get_self_id", None)
        if not callable(getter):
            return False
        try:
            self_id = str(getter() or "").strip()
        except Exception:
            return False
        return bool(self_id) and self_id == str(sender_id or "").strip()

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
            if self._is_self_message(event, sender_id):
                self._log_message_capture_diag("skip:self_message", event, message_text)
                return
            event_metadata = extract_learning_event_metadata(event)
            if should_ignore_learning_sample(
                message_text,
                sender_id=sender_id,
                **event_metadata,
            ):
                boundary_queued = self._queue_style_context_capture(group_id, sender_id, "", event)
                logger.debug(f"检测到指令或系统模板消息，跳过学习数据收集: {message_text[:80]}")
                self._log_message_capture_diag(
                    "queued:style_boundary" if boundary_queued else "skip:system_or_command_sample",
                    event, message_text,
                )
                return
            self._log_message_capture_diag("accepted:event_received", event, message_text)

            # 好感度处理（后台，仅 at/唤醒消息）
            pipeline = getattr(self, '_pipeline', None)
            qq_filter = getattr(self, 'qq_filter', None)
            is_target = not qq_filter or qq_filter.should_collect_message(sender_id, group_id)
            cmd_filter = getattr(self, '_command_filter', None)
            is_command = bool(cmd_filter and cmd_filter.is_astrbot_command(event))
            if (
                event.is_at_or_wake_command
                and self.plugin_config
                and self.plugin_config.enable_affection_system
                and pipeline
                and is_target
                and not is_command
            ):
                self._track_task(asyncio.create_task(
                    pipeline.process_affection(group_id, sender_id, message_text)
                ))

            if not self.plugin_config or not self.plugin_config.enable_message_capture:
                self._log_message_capture_diag("skip:capture_disabled", event, message_text, level="info")
                return

            # 命令过滤
            if is_command:
                boundary_queued = self._queue_style_context_capture(group_id, sender_id, "", event)
                logger.debug(f"检测到AstrBot命令，跳过学习数据收集: {message_text}")
                self._log_message_capture_diag(
                    "queued:style_boundary" if boundary_queued else "skip:command_message", event, message_text,
                )
                return

            if not is_target:
                if self._queue_style_context_capture(group_id, sender_id, message_text, event):
                    self._log_message_capture_diag("queued:style_context", event, message_text)
                    return
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
        # Keep the general hook switch unchanged. This only advertises the
        # read-only query tool and never starts a learning/model request.
        add_affection_guidance(self, event, req)
        handler = getattr(self, '_hook_handler', None)
        if handler:
            await handler.handle(event, req)

    @filter.llm_tool(name="query_affection")
    async def query_affection(self, event: AstrMessageEvent, mode: str = "user",
                             user_id: str = "", group_id: str = "", limit: int = 10) -> str:
        """从 self-learning 数据库只读查询好感度或当前群排行，不使用记忆猜分，也不修改分数。

        Args:
            mode(str): user 查询本人或指定用户；ranking 查询当前群排名（管理员）。
            user_id(str): user 模式的 QQ 号，留空查本人；查询他人仅限管理员。
            group_id(str): 留空为当前群/私聊范围；管理员私聊可明确指定已加入的群号，分数不跨群合并。
            limit(int): 排行返回数量，1 至 20，默认 10。
        """
        return json.dumps(await query_affection_snapshot(self,event,mode,user_id,group_id,limit),ensure_ascii=False)

    # Bot 出站消息捕获

    @filter.after_message_sent()
    @monitored
    async def on_bot_message_sent(self, event: AstrMessageEvent, *_args):
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
            # 黑名单群组不计入 few-shot 对话对（只查黑名单，不受白名单限制影响）
            qq_filter = getattr(self, 'qq_filter', None)
            if qq_filter and qq_filter.is_blacklisted("bot", group_id):
                logger.debug(f"群组 {group_id} 在学习黑名单中，跳过 Bot 出站消息保存")
                return
            await db.save_bot_message(
                group_id=group_id,
                message=bot_text,
            )
        except Exception as e:
            logger.warning(f"保存Bot出站消息失败: {e}", exc_info=True)

    # 命令处理器（薄委托）

    @filter.command("learning_status")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def learning_status_command(self, event: AstrMessageEvent):
        """查看学习状态"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.learning_status(event):
            yield result

    @filter.command("start_learning")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def start_learning_command(self, event: AstrMessageEvent):
        """手动启动学习"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.start_learning(event):
            yield result

    @filter.command("stop_learning")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def stop_learning_command(self, event: AstrMessageEvent):
        """停止学习"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.stop_learning(event):
            yield result

    @filter.command("force_learning")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def force_learning_command(self, event: AstrMessageEvent):
        """强制执行一次学习周期"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.force_learning(event):
            yield result

    @filter.command("remember")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def remember_command(self, event: AstrMessageEvent):
        """手动记住引用对话及上下文，并链入表达方式和对话示例"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.remember(event):
            yield result

    @filter.command("clean_rag_cache")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def clean_rag_cache_command(self, event: AstrMessageEvent):
        """清理 LightRAG LLM 响应缓存"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.clean_rag_cache(event):
            yield result

    @filter.command("affection_status")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def affection_status_command(self, event: AstrMessageEvent):
        """查看好感度状态"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.affection_status(event):
            yield result

    @filter.command("set_mood")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def set_mood_command(self, event: AstrMessageEvent):
        """手动设置bot情绪"""
        if not self._command_handlers:
            yield event.plain_result("插件服务未就绪，请检查启动日志")
            return
        async for result in self._command_handlers.set_mood(event):
            yield result
