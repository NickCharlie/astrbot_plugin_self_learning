"""插件全生命周期编排 — 服务初始化 → 异步启动 → 有序关停"""
import os
import json
import asyncio
from typing import Any, Dict, TYPE_CHECKING

from astrbot.api import logger

from .factory import FactoryManager
from ..exceptions import SelfLearningError
from ..statics.messages import StatusMessages, LogMessages

if TYPE_CHECKING:
    pass # 避免循环导入


class PluginLifecycle:
    """插件全生命周期编排：初始化 → 启动 → 关停

    将 main.py 中的 _initialize_services / _setup_internal_components /
    on_load / terminate 逻辑统一到一处。
    """

    def __init__(self, plugin: Any):
        """
        Args:
            plugin: SelfLearningPlugin 实例（回引，用于设置属性）
        """
        self._plugin = plugin
        self._webui_manager = None # Phase 2 WebUIManager 延迟创建

    # Phase 1: 同步初始化（__init__ 阶段调用）

    def bootstrap(
        self,
        plugin_config: Any,
        context: Any,
        group_id_to_unified_origin: Dict[str, str],
    ) -> None:
        """同步初始化：创建全部服务并注入到 plugin 实例上"""
        p = self._plugin # 简写

        try:
            # ------ FactoryManager 初始化 ------
            p.factory_manager = FactoryManager()
            p.factory_manager.initialize_factories(plugin_config, context)
            p.service_factory = p.factory_manager.get_service_factory()

            # ------ ServiceFactory 创建核心服务 ------
            p.db_manager = p.service_factory.create_database_manager()
            p.message_collector = p.service_factory.create_message_collector()
            p.multidimensional_analyzer = p.service_factory.create_multidimensional_analyzer()
            p.style_analyzer = p.service_factory.create_style_analyzer()
            p.quality_monitor = p.service_factory.create_quality_monitor()
            p.progressive_learning = p.service_factory.create_progressive_learning()
            p.ml_analyzer = p.service_factory.create_ml_analyzer()
            p.persona_manager = p.service_factory.create_persona_manager()
            p.diversity_manager = p.service_factory.create_response_diversity_manager()

            # ------ ComponentFactory 创建高级服务 ------
            component_factory = p.factory_manager.get_component_factory()
            p.advanced_learning = component_factory.create_advanced_learning_service()
            p.enhanced_interaction = component_factory.create_enhanced_interaction_service()
            p.intelligence_enhancement = component_factory.create_intelligence_enhancement_service()
            p.affection_manager = component_factory.create_affection_manager_service()

            # ------ 条件创建：对话目标管理器 ------
            logger.info(
                f"[初始化] enable_goal_driven_chat={plugin_config.enable_goal_driven_chat}"
            )
            if plugin_config.enable_goal_driven_chat:
                try:
                    p.conversation_goal_manager = (
                        component_factory.create_conversation_goal_manager()
                    )
                    logger.info("对话目标管理器已初始化")
                except Exception as e:
                    logger.error(f"创建对话目标管理器失败: {e}", exc_info=True)
                    p.conversation_goal_manager = None
            else:
                p.conversation_goal_manager = None
                logger.info("对话目标管理器未启用")

            # ------ 社交上下文注入器（必须在 intelligent_responder 之前）------
            p.social_context_injector = component_factory.create_social_context_injector()

            # ------ 黑话服务 ------
            from ..services.jargon import (
                JargonQueryService,
                JargonMinerManager,
                JargonStatisticalFilter,
            )

            p.jargon_query_service = JargonQueryService(
                db_manager=p.db_manager, cache_ttl=60
            )
            logger.info("黑话查询服务已初始化（带60秒缓存）")

            p.jargon_miner_manager = JargonMinerManager(
                llm_adapter=p.service_factory.create_framework_llm_adapter(),
                db_manager=p.db_manager,
                config=plugin_config,
            )
            logger.info("黑话挖掘管理器已初始化")

            p.jargon_statistical_filter = JargonStatisticalFilter()
            logger.info("黑话统计预筛器已初始化")

            # ------ V2 架构集成（条件创建）------
            p.v2_integration = None
            logger.info(
                f"[V2] Config check: knowledge_engine='{plugin_config.knowledge_engine}', "
                f"memory_engine='{plugin_config.memory_engine}'"
            )
            if (
                plugin_config.knowledge_engine != "legacy"
                or plugin_config.memory_engine != "legacy"
            ):
                try:
                    from ..services.core_learning import V2LearningIntegration

                    llm_adapter = p.service_factory.create_framework_llm_adapter()
                    p.v2_integration = V2LearningIntegration(
                        config=plugin_config,
                        llm_adapter=llm_adapter,
                        db_manager=p.db_manager,
                        context=context,
                    )
                    logger.info(
                        f"V2LearningIntegration initialised "
                        f"(knowledge={plugin_config.knowledge_engine}, "
                        f"memory={plugin_config.memory_engine})"
                    )
                except Exception as exc:
                    logger.warning(
                        f"V2LearningIntegration init failed, v2 features disabled: {exc}"
                    )
                    p.v2_integration = None

            # ------ 依赖后创建的服务 ------
            p.intelligent_responder = p.service_factory.create_intelligent_responder()
            p.temporary_persona_updater = p.service_factory.create_temporary_persona_updater()

            # ------ group_id 映射表传递 ------
            p.temporary_persona_updater.group_id_to_unified_origin = (
                group_id_to_unified_origin
            )
            if p.progressive_learning:
                p.progressive_learning.group_id_to_unified_origin = (
                    group_id_to_unified_origin
                )
            if p.persona_manager:
                p.persona_manager.group_id_to_unified_origin = (
                    group_id_to_unified_origin
                )
            logger.info("已将 group_id 映射表传递给服务组件")

            # ------ LLM 适配器（状态报告用）------
            p.llm_adapter = p.service_factory.create_framework_llm_adapter()

            # ------ 内部组件（QQ过滤/消息过滤/人格更新/调度器）------
            self._setup_internal_components(plugin_config, context, group_id_to_unified_origin)

            # ------ 提取的服务模块 ------
            from ..services.learning.dialog_analyzer import DialogAnalyzer
            from ..services.learning.realtime_processor import RealtimeProcessor
            from ..services.learning.group_orchestrator import GroupLearningOrchestrator
            from ..services.hooks.llm_hook_handler import LLMHookHandler

            p._dialog_analyzer = DialogAnalyzer(p.factory_manager, p.db_manager)
            p._realtime_processor = RealtimeProcessor(
                plugin_config=plugin_config,
                message_collector=p.message_collector,
                multidimensional_analyzer=p.multidimensional_analyzer,
                persona_manager=p.persona_manager,
                temporary_persona_updater=p.temporary_persona_updater,
                dialog_analyzer=p._dialog_analyzer,
                learning_stats=p.learning_stats,
                factory_manager=p.factory_manager,
                db_manager=p.db_manager,
            )
            p._group_orchestrator = GroupLearningOrchestrator(
                plugin_config=plugin_config,
                message_collector=p.message_collector,
                progressive_learning=p.progressive_learning,
                qq_filter=p.qq_filter,
                db_manager=p.db_manager,
            )
            p._hook_handler = LLMHookHandler(
                plugin_config=plugin_config,
                diversity_manager=getattr(p, "diversity_manager", None),
                social_context_injector=getattr(p, "social_context_injector", None),
                v2_integration=getattr(p, "v2_integration", None),
                jargon_query_service=getattr(p, "jargon_query_service", None),
                temporary_persona_updater=getattr(p, "temporary_persona_updater", None),
                perf_tracker=p._perf_tracker,
                group_id_to_unified_origin=group_id_to_unified_origin,
                db_manager=getattr(p, "db_manager", None),
            )

            # ------ 消息处理流水线 ------
            from ..services.learning.message_pipeline import MessagePipeline

            p._pipeline = MessagePipeline(
                plugin_config=plugin_config,
                message_collector=p.message_collector,
                enhanced_interaction=p.enhanced_interaction,
                jargon_miner_manager=getattr(p, "jargon_miner_manager", None),
                jargon_statistical_filter=getattr(p, "jargon_statistical_filter", None),
                v2_integration=getattr(p, "v2_integration", None),
                realtime_processor=p._realtime_processor,
                group_orchestrator=p._group_orchestrator,
                conversation_goal_manager=getattr(p, "conversation_goal_manager", None),
                affection_manager=p.affection_manager,
                db_manager=p.db_manager,
            )

            # ------ 命令处理器 ------
            from ..services.commands import PluginCommandHandlers, CommandFilter

            p._command_handlers = PluginCommandHandlers(
                plugin_config=plugin_config,
                service_factory=p.service_factory,
                message_collector=p.message_collector,
                persona_manager=p.persona_manager,
                progressive_learning=p.progressive_learning,
                affection_manager=p.affection_manager,
                temporary_persona_updater=p.temporary_persona_updater,
                db_manager=p.db_manager,
                llm_adapter=p.llm_adapter,
            )
            p._command_filter = CommandFilter()

            # ------ WebUI 管理器 ------
            from ..webui.manager import WebUIManager

            self._webui_manager = WebUIManager(
                plugin_config=plugin_config,
                context=context,
                factory_manager=p.factory_manager,
                perf_tracker=p._perf_tracker,
                group_id_to_unified_origin=group_id_to_unified_origin,
            )
            need_immediate_start = self._webui_manager.create_server()
            if need_immediate_start:
                asyncio.create_task(self._webui_manager.immediate_start(p.db_manager))

            # ------ 自动学习启动（必须在 _group_orchestrator 创建之后）------
            if plugin_config.enable_auto_learning:
                asyncio.create_task(p._group_orchestrator.delayed_auto_start_learning())

            logger.info(StatusMessages.FACTORY_SERVICES_INIT_COMPLETE)

        except SelfLearningError as sle:
            logger.error(StatusMessages.SERVICES_INIT_FAILED.format(error=sle))
            raise
        except (TypeError, ValueError) as e:
            logger.error(
                StatusMessages.CONFIG_TYPE_ERROR.format(error=e), exc_info=True
            )
            raise SelfLearningError(
                StatusMessages.INIT_FAILED_GENERIC.format(error=str(e))
            ) from e
        except Exception as e:
            logger.error(
                StatusMessages.UNKNOWN_INIT_ERROR.format(error=e), exc_info=True
            )
            raise SelfLearningError(
                StatusMessages.INIT_FAILED_GENERIC.format(error=str(e))
            ) from e

    def _setup_internal_components(
        self,
        plugin_config: Any,
        context: Any,
        group_id_to_unified_origin: Dict[str, str],
    ) -> None:
        """设置内部组件 — QQ 过滤 / 消息过滤 / 人格更新器 / 学习调度器"""
        p = self._plugin
        component_factory = p.factory_manager.get_component_factory()
        p.component_factory = component_factory

        p.qq_filter = component_factory.create_qq_filter()
        p.message_filter = component_factory.create_message_filter(context)

        persona_backup_manager_instance = p.service_factory.create_persona_backup_manager()
        p.persona_updater = component_factory.create_persona_updater(
            context, persona_backup_manager_instance
        )

        p.persona_updater.group_id_to_unified_origin = group_id_to_unified_origin
        persona_backup_manager_instance.group_id_to_unified_origin = (
            group_id_to_unified_origin
        )

        p.learning_scheduler = component_factory.create_learning_scheduler(p)
        p.background_tasks = set()

        asyncio.create_task(self._delayed_provider_reinitialization())

    # Phase 2: 异步启动（on_load 阶段调用）

    async def on_load(self) -> None:
        """异步启动：DB（带重试）+ 服务 + WebUI"""
        p = self._plugin
        plugin_config = p.plugin_config

        logger.info(StatusMessages.ON_LOAD_START)

        # ------ DB 启动（带重试）------
        db_started = False
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"尝试启动数据库管理器 (第 {attempt + 1}/{max_retries} 次)")
                db_started = await p.db_manager.start()
                if db_started:
                    logger.info(StatusMessages.DB_MANAGER_STARTED)
                    break
                else:
                    logger.warning(
                        f"数据库管理器启动返回 False (尝试 {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
            except Exception as e:
                logger.error(
                    f"数据库启动异常 (尝试 {attempt + 1}/{max_retries}): {e}",
                    exc_info=True,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        if not db_started:
            logger.error(
                StatusMessages.DB_MANAGER_START_FAILED.format(error="所有重试均失败")
            )
            logger.warning("插件将在数据库功能受限的情况下继续运行")

        # ------ 好感度管理服务 ------
        if plugin_config.enable_affection_system and getattr(p, "affection_manager", None):
            try:
                await p.affection_manager.start()
                logger.info("好感度管理服务启动成功")
            except Exception as e:
                logger.error(f"好感度管理服务启动失败: {e}", exc_info=True)

        # ------ V2 学习集成 ------
        if getattr(p, "v2_integration", None):
            try:
                await p.v2_integration.start()
                logger.info("V2LearningIntegration started successfully")
            except Exception as e:
                logger.error(f"V2LearningIntegration start failed: {e}", exc_info=True)

        # ------ 函数级性能监控 ------
        if plugin_config.debug_mode:
            try:
                from ..services.monitoring.instrumentation import set_debug_mode
                set_debug_mode(True)
                logger.info("函数级性能监控已启用 (debug_mode=True)")
            except ImportError:
                logger.warning(
                    "prometheus_client 未安装，函数级性能监控不可用。"
                    "安装 prometheus_client 后重启即可启用。"
                )

        # ------ WebUI ------
        if self._webui_manager:
            await self._webui_manager.setup_and_start()

        logger.info(StatusMessages.PLUGIN_LOAD_COMPLETE)

    # Phase 3: 有序关停（terminate 阶段调用）

    _STEP_TIMEOUT = 8  # 每个关停步骤的超时秒数
    _TASK_CANCEL_TIMEOUT = 3  # 每个后台任务取消等待的超时秒数

    async def _safe_step(self, label: str, coro, timeout: float = None) -> None:
        """执行一个关停步骤，超时或异常均不阻塞后续步骤"""
        if timeout is None:
            timeout = self._STEP_TIMEOUT
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            logger.info(f"{label} 完成")
        except asyncio.TimeoutError:
            logger.warning(f"{label} 超时 ({timeout}s)，跳过")
        except Exception as e:
            logger.error(f"{label} 失败: {e}")

    async def shutdown(self) -> None:
        """有序关停所有服务（每步带超时，避免卡死）"""
        p = self._plugin
        try:
            logger.info("开始插件清理工作...")

            # 1. 停止学习任务
            logger.info("停止所有学习任务...")
            if getattr(p, "_group_orchestrator", None):
                await self._safe_step(
                    "停止学习任务",
                    p._group_orchestrator.cancel_all(),
                )

            # 2. 停止学习调度器
            if hasattr(p, "learning_scheduler"):
                await self._safe_step(
                    "停止学习调度器",
                    p.learning_scheduler.stop(),
                )

            # 3. 取消后台任务（每个任务单独超时）
            logger.info("取消所有后台任务...")
            for task in list(p.background_tasks):
                try:
                    if not task.done():
                        task.cancel()
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(task),
                                timeout=self._TASK_CANCEL_TIMEOUT,
                            )
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass
                except Exception as e:
                    logger.error(
                        LogMessages.BACKGROUND_TASK_CANCEL_ERROR.format(error=e)
                    )
            p.background_tasks.clear()

            # 4. 停止服务工厂
            if hasattr(p, "factory_manager"):
                await self._safe_step(
                    "清理服务工厂",
                    p.factory_manager.cleanup(),
                )

            # 4.5 停止 V2
            if getattr(p, "v2_integration", None):
                await self._safe_step(
                    "停止 V2LearningIntegration",
                    p.v2_integration.stop(),
                )

            # 4.6 重置单例
            try:
                from ..services.state import EnhancedMemoryGraphManager

                EnhancedMemoryGraphManager._instance = None
                EnhancedMemoryGraphManager._initialized = False
                logger.info("MemoryGraphManager 单例已重置")
            except Exception:
                pass

            # 5. 清理临时人格
            if hasattr(p, "temporary_persona_updater"):
                await self._safe_step(
                    "清理临时人格",
                    p.temporary_persona_updater.cleanup_temp_personas(),
                )

            # 6. 保存状态
            if hasattr(p, "message_collector"):
                await self._safe_step(
                    "保存消息收集器状态",
                    p.message_collector.save_state(),
                )

            # 7. 停止 WebUI
            if self._webui_manager:
                await self._safe_step(
                    "停止 WebUI",
                    self._webui_manager.stop(),
                )

            # 8. 保存配置
            try:
                config_path = os.path.join(p.plugin_config.data_dir, "config.json")
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(p.plugin_config.to_dict(), f, ensure_ascii=False, indent=2)
                logger.info(LogMessages.PLUGIN_CONFIG_SAVED)
            except Exception as e:
                logger.error(f"保存配置失败: {e}")

            logger.info(LogMessages.PLUGIN_UNLOAD_SUCCESS)

        except Exception as e:
            logger.error(
                LogMessages.PLUGIN_UNLOAD_CLEANUP_FAILED.format(error=e),
                exc_info=True,
            )

    # 辅助异步方法

    async def _delayed_provider_reinitialization(self) -> None:
        """延迟重新初始化提供商配置，解决重启后配置丢失问题"""
        p = self._plugin
        try:
            await asyncio.sleep(10)

            if getattr(p, "llm_adapter", None):
                p.llm_adapter.initialize_providers(p.plugin_config)
                logger.info("延迟重新初始化提供商配置完成")

                if p.llm_adapter.providers_configured == 0:
                    logger.warning("重新初始化后仍然没有配置任何提供商，请检查配置")
                    await asyncio.sleep(30)
                    p.llm_adapter.initialize_providers(p.plugin_config)
                    logger.info("第二次尝试重新初始化提供商配置")
                else:
                    logger.info(
                        f"成功配置了 {p.llm_adapter.providers_configured} 个提供商"
                    )
        except Exception as e:
            logger.error(f"延迟重新初始化提供商配置失败: {e}")

    async def _delayed_start_learning(self, group_id: str) -> None:
        """延迟启动学习服务"""
        p = self._plugin
        try:
            await asyncio.sleep(3)
            await p.service_factory.initialize_all_services()
            await p.progressive_learning.start_learning(group_id)
            logger.info(
                StatusMessages.AUTO_LEARNING_SCHEDULER_STARTED.format(
                    group_id=group_id
                )
            )
        except Exception as e:
            logger.error(
                StatusMessages.LEARNING_SERVICE_START_FAILED.format(
                    group_id=group_id, error=e
                )
            )
