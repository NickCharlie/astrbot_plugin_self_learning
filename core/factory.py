"""
服务工厂 - 工厂模式实现，避免循环导入
"""
from typing import Dict, Any, Optional
import asyncio
import functools
import json # 导入json模块，因为MessageFilter中使用了

from astrbot.api.star import Context
from astrbot.api import logger # 使用框架提供的logger

from .interfaces import (
    IServiceFactory, IMessageCollector, IStyleAnalyzer, ILearningStrategy,
    IQualityMonitor, IPersonaManager, IPersonaUpdater, IMLAnalyzer, IIntelligentResponder,
    IMessageRelationshipAnalyzer, LearningStrategyType
)
from .patterns import StrategyFactory, ServiceRegistry
from .framework_llm_adapter import FrameworkLLMAdapter # 导入框架LLM适配器

# 使用单例模式导入配置和异常
from ..config import PluginConfig
from ..exceptions import ServiceError
from ..statics import prompts
from ..utils.json_utils import safe_parse_llm_json


def cached_service(key):
    """Decorator that caches create_* return values in self._service_cache."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if key in self._service_cache:
                return self._service_cache[key]
            result = func(self, *args, **kwargs)
            if result is not None:
                self._service_cache[key] = result
            return result
        return wrapper
    return decorator


class ServiceFactory(IServiceFactory):
    """主要服务工厂 - 创建和管理所有服务实例"""
    
    def __init__(self, config: PluginConfig, context: Context):
        self.config = config
        self.context = context
        self._logger = logger
        self._registry = ServiceRegistry(
            service_stop_timeout=config.service_stop_timeout,
        )

        # 服务实例缓存
        self._service_cache: Dict[str, Any] = {}
        
        # 框架适配器
        self._framework_llm_adapter: Optional[FrameworkLLMAdapter] = None

    def create_framework_llm_adapter(self) -> FrameworkLLMAdapter:
        """创建或获取框架LLM适配器（带延迟初始化）"""
        if self._framework_llm_adapter is None:
            try:
                self._logger.info("初始化框架LLM适配器...")

                self._framework_llm_adapter = FrameworkLLMAdapter(self.context)
                self._framework_llm_adapter.initialize_providers(self.config)

                # 检查是否成功配置了至少一个提供商
                if self._framework_llm_adapter.providers_configured > 0:
                    self._logger.info(f" 框架LLM适配器初始化成功，已配置 {self._framework_llm_adapter.providers_configured} 个提供商")
                else:
                    # 重要变更：Provider未配置时不抛出异常，允许延迟初始化
                    self._logger.warning(
                        " 框架LLM适配器初始化时未找到可用的Provider。\n"
                        " 原因可能是：\n"
                        " 1. AstrBot的Provider系统尚未完全初始化（插件加载时序问题）\n"
                        " 2. 配置文件中未指定filter_provider_id/refine_provider_id\n"
                        " 3. 指定的Provider ID不存在\n"
                        " 插件将继续加载，Provider会在实际使用时自动重试初始化。"
                    )
                    # 标记为需要延迟初始化
                    self._framework_llm_adapter._needs_lazy_init = True

            except Exception as e:
                self._logger.warning(
                    f" 初始化LLM适配器时发生异常: {e}\n"
                    " 插件将继续加载，LLM功能会在实际调用时重试初始化。",
                    exc_info=self.config.debug_mode # 仅在debug模式显示完整堆栈
                )
                # 创建一个最小化的适配器实例，允许插件继续加载
                self._framework_llm_adapter = FrameworkLLMAdapter(self.context)
                self._framework_llm_adapter._needs_lazy_init = True

        return self._framework_llm_adapter

    def get_prompts(self) -> Any:
        """获取 Prompt 静态数据"""
        return prompts

    @cached_service("message_collector")
    def create_message_collector(self) -> IMessageCollector:
        """创建消息收集器"""
        try:
            # 单例模式动态导入避免循环依赖
            from ..services.core_learning import MessageCollectorService

            service = MessageCollectorService(self.config, self.context, self.create_database_manager()) # 传递 DatabaseManager
            self._registry.register_service("message_collector", service)
            
            self._logger.info("创建消息收集器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入消息收集器失败: {e}", exc_info=True)
            raise ServiceError(f"创建消息收集器失败: {str(e)}")
    
    @cached_service("style_analyzer")
    def create_style_analyzer(self) -> IStyleAnalyzer:
        """创建风格分析器 - 优先使用MaiBot增强版本"""
        try:
            # 如果启用了MaiBot增强功能，使用MaiBot适配器
            if getattr(self.config, 'enable_maibot_features', False):
                try:
                    from ..services.integration import MaiBotStyleAnalyzer
                    service = MaiBotStyleAnalyzer(
                        self.config,
                        self.create_database_manager(),
                        context=self.context,
                        llm_adapter=self.create_framework_llm_adapter()
                    )
                    self._registry.register_service("style_analyzer", service)
                    self._logger.info("创建MaiBot风格分析器成功")
                    return service
                except ImportError as e:
                    self._logger.warning(f"MaiBot适配器不可用，回退到默认实现: {e}")

            # 回退到默认实现
            from ..services.response import StyleAnalyzerService

            # 传递 DatabaseManager 和框架适配器
            service = StyleAnalyzerService(
                self.config,
                self.context,
                self.create_database_manager(),
                llm_adapter=self.create_framework_llm_adapter(), # 使用框架适配器
                prompts=self.get_prompts() # 传递 prompts
            )
            self._registry.register_service("style_analyzer", service)
            
            self._logger.info("创建风格分析器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入风格分析器失败: {e}", exc_info=True)
            raise ServiceError(f"创建风格分析器失败: {str(e)}")
    
    @cached_service("message_relationship_analyzer")
    def create_message_relationship_analyzer(self):
        """创建消息关系分析器"""
        try:
            from ..services.social import MessageRelationshipAnalyzer

            service = MessageRelationshipAnalyzer(
                self.config,
                self.context,
                llm_adapter=self.create_framework_llm_adapter()
            )
            self._registry.register_service("message_relationship_analyzer", service)
            
            self._logger.info("创建消息关系分析器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入消息关系分析器失败: {e}", exc_info=True)
            raise ServiceError(f"创建消息关系分析器失败: {str(e)}")

    def create_learning_strategy(self, strategy_type: str) -> ILearningStrategy:
        """创建学习策略 - 优先使用MaiBot增强版本"""
        try:
            # 如果启用了MaiBot增强功能，使用MaiBot学习策略
            if getattr(self.config, 'enable_maibot_features', False):
                try:
                    from ..services.integration import MaiBotLearningStrategy
                    strategy = MaiBotLearningStrategy(self.config, self.create_database_manager())
                    self._logger.info("创建MaiBot学习策略成功")
                    return strategy
                except ImportError as e:
                    self._logger.warning(f"MaiBot学习策略不可用，回退到默认实现: {e}")
            
            # 转换字符串为枚举
            if isinstance(strategy_type, str):
                strategy_enum = LearningStrategyType(strategy_type)
            else:
                strategy_enum = strategy_type
            
            # 使用策略工厂创建
            strategy_config = {
                'batch_size': self.config.max_messages_per_batch,
                'min_messages': self.config.min_messages_for_learning,
                'min_interval_hours': self.config.learning_interval_hours
            }
            
            strategy = StrategyFactory.create_strategy(strategy_enum, strategy_config)
            self._logger.info(f"创建学习策略成功: {strategy_type}")
            
            return strategy
            
        except ValueError as e:
            self._logger.error(f"不支持的策略类型: {strategy_type}", exc_info=True)
            raise ServiceError(f"创建学习策略失败: {str(e)}")
    
    @cached_service("quality_monitor")
    def create_quality_monitor(self) -> IQualityMonitor:
        """创建质量监控器 - 优先使用MaiBot增强版本"""
        try:
            # 如果启用了MaiBot增强功能，使用MaiBot质量监控器
            if getattr(self.config, 'enable_maibot_features', False):
                try:
                    from ..services.integration import MaiBotQualityMonitor
                    service = MaiBotQualityMonitor(self.config, self.create_database_manager())
                    self._registry.register_service("quality_monitor", service)
                    self._logger.info("创建MaiBot质量监控器成功")
                    return service
                except ImportError as e:
                    self._logger.warning(f"MaiBot质量监控器不可用，回退到默认实现: {e}")

            # 回退到默认实现
            from ..services.quality import LearningQualityMonitor

            service = LearningQualityMonitor(
                self.config,
                self.context,
                llm_adapter=self.create_framework_llm_adapter(), # 使用框架适配器
                prompts=self.get_prompts() # 传递 prompts
            )
            self._registry.register_service("quality_monitor", service)
            
            self._logger.info("创建质量监控器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入质量监控器失败: {e}", exc_info=True)
            raise ServiceError(f"创建质量监控器失败: {str(e)}")
    
    @cached_service("database_manager")
    def create_database_manager(self):
        """创建数据库管理器 - 根据配置选择实现"""
        try:
            from ..services.database import SQLAlchemyDatabaseManager

            service = SQLAlchemyDatabaseManager(self.config, self.context)
            self._registry.register_service("database_manager", service)

            self._logger.info(f"创建数据库管理器成功 (实现: SQLAlchemyDatabaseManager)")
            return service

        except ImportError as e:
            self._logger.error(f"导入数据库管理器失败: {e}", exc_info=True)
            raise ServiceError(f"创建数据库管理器失败: {str(e)}")
    
    @cached_service("ml_analyzer")
    def create_ml_analyzer(self) -> IMLAnalyzer:
        """创建ML分析器"""
        try:
            from ..services.analysis import LightweightMLAnalyzer

            # 需要数据库管理器
            db_manager = self.create_database_manager()

            # 获取临时人格更新器实例
            temporary_persona_updater = self.create_temporary_persona_updater()

            service = LightweightMLAnalyzer(
                self.config,
                db_manager,
                llm_adapter=self.create_framework_llm_adapter(), # 使用框架适配器
                prompts=self.get_prompts(), # 传递 prompts
                temporary_persona_updater=temporary_persona_updater # 传递临时人格更新器
            )
            
            self._logger.info("创建ML分析器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入ML分析器失败: {e}", exc_info=True)
            raise ServiceError(f"创建ML分析器失败: {str(e)}")
    
    @cached_service("intelligent_responder")
    def create_intelligent_responder(self) -> IIntelligentResponder:
        """创建智能回复器"""
        try:
            from ..services.response import IntelligentResponder

            # 需要数据库管理器
            db_manager = self.create_database_manager()

            # 获取好感度管理器（如果已创建）
            affection_manager = self._service_cache.get("affection_manager")

            # 获取多样性管理器（如果已创建）
            diversity_manager = self._service_cache.get("response_diversity_manager")

            # 获取社交上下文注入器（如果已创建）
            social_context_injector = self._service_cache.get("social_context_injector")

            service = IntelligentResponder(
                self.config,
                self.context,
                db_manager,
                llm_adapter=self.create_framework_llm_adapter(), # 传递框架适配器
                prompts=self.get_prompts(), # 传递 prompts
                affection_manager=affection_manager, # 传递好感度管理器
                diversity_manager=diversity_manager, # 传递多样性管理器
                social_context_injector=social_context_injector # 传递社交上下文注入器
            )

            self._logger.info("创建智能回复器成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入智能回复器失败: {e}", exc_info=True)
            raise ServiceError(f"创建智能回复器失败: {str(e)}")
    
    @cached_service("persona_manager")
    def create_persona_manager(self) -> IPersonaManager:
        """创建人格管理器"""
        try:
            from ..services.persona import PersonaManagerService # 导入 PersonaManagerService

            # 创建依赖的服务
            persona_updater = self.create_persona_updater()
            persona_backup_manager = self.create_persona_backup_manager()

            service = PersonaManagerService(self.config, self.context, persona_updater, persona_backup_manager)
            self._registry.register_service("persona_manager", service) # 注册服务
            
            self._logger.info("创建人格管理器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入人格管理器失败: {e}", exc_info=True)
            raise ServiceError(f"创建人格管理器失败: {str(e)}")
    
    @cached_service("persona_manager_updater")
    def create_persona_manager_updater(self):
        """创建PersonaManager增量更新器"""
        try:
            from ..services.persona import PersonaManagerUpdater

            service = PersonaManagerUpdater(self.config, self.context)
            self._registry.register_service("persona_manager_updater", service)
            
            self._logger.info("创建PersonaManager更新器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入PersonaManager更新器失败: {e}", exc_info=True)
            raise ServiceError(f"创建PersonaManager更新器失败: {str(e)}")
    
    @cached_service("multidimensional_analyzer")
    def create_multidimensional_analyzer(self):
        """创建多维度分析器"""
        try:
            from ..services.analysis import MultidimensionalAnalyzer

            db_manager = self.create_database_manager() # 获取 DatabaseManager 实例

            # 使用框架LLM适配器
            llm_adapter = self.create_framework_llm_adapter()

            # 获取临时人格更新器实例
            temporary_persona_updater = self.create_temporary_persona_updater()

            service = MultidimensionalAnalyzer(
                self.config,
                db_manager,
                self.context,
                llm_adapter=llm_adapter, # 传递框架适配器
                prompts=self.get_prompts(), # 传递 prompts
                temporary_persona_updater=temporary_persona_updater # 传递临时人格更新器
            )
            
            self._logger.info("创建多维度分析器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入多维度分析器失败: {e}", exc_info=True)
            raise ServiceError(f"创建多维度分析器失败: {str(e)}")

    @cached_service("progressive_learning")
    def create_progressive_learning(self):
        """创建渐进式学习服务"""
        try:
            from ..services.core_learning import ProgressiveLearningService

            # Directly pass the database manager
            db_manager = self.create_database_manager()

            service = ProgressiveLearningService(
                self.config,
                self.context,
                db_manager=db_manager, # 传递 db_manager 实例
                message_collector=self.create_message_collector(),
                multidimensional_analyzer=self.create_multidimensional_analyzer(),
                style_analyzer=self.create_style_analyzer(),
                quality_monitor=self.create_quality_monitor(),
                persona_manager=self.create_persona_manager(), # 传递 persona_manager 实例
                ml_analyzer=self.create_ml_analyzer(), # 传递 ml_analyzer 实例
                prompts=self.get_prompts() # 传递 prompts
            )
            self._registry.register_service("progressive_learning", service)
            
            self._logger.info("创建渐进式学习服务成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入渐进式学习服务失败: {e}", exc_info=True)
            raise ServiceError(f"创建渐进式学习服务失败: {str(e)}")

    
    @cached_service("persona_backup_manager")
    def create_persona_backup_manager(self):
        """创建人格备份管理器"""
        try:
            from ..services.persona import PersonaBackupManager
            db_manager = self.create_database_manager()
            service = PersonaBackupManager(self.config, self.context, db_manager)
            self._registry.register_service("persona_backup_manager", service)
            self._logger.info("创建人格备份管理器成功")
            return service
        except ImportError as e:
            self._logger.error(f"导入人格备份管理器失败: {e}", exc_info=True)
            raise ServiceError(f"创建人格备份管理器失败: {str(e)}")

    @cached_service("temporary_persona_updater")
    def create_temporary_persona_updater(self):
        """创建临时人格更新器"""
        try:
            from ..services.persona import TemporaryPersonaUpdater

            # 获取依赖的服务
            persona_updater = self.create_persona_updater()
            backup_manager = self.create_persona_backup_manager()
            db_manager = self.create_database_manager()

            service = TemporaryPersonaUpdater(
                self.config,
                self.context,
                persona_updater,
                backup_manager,
                db_manager
            )
            self._registry.register_service("temporary_persona_updater", service)
            
            self._logger.info("创建临时人格更新器成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入临时人格更新器失败: {e}", exc_info=True)
            raise ServiceError(f"创建临时人格更新器失败: {str(e)}")

    @cached_service("persona_updater")
    def create_persona_updater(self) -> IPersonaUpdater: # 修改返回类型为 IPersonaUpdater
        """创建人格更新器"""
        try:
            from ..services.persona import PersonaUpdater
            backup_manager = self.create_persona_backup_manager()
            service = PersonaUpdater(
                self.config,
                self.context,
                backup_manager,
                None, # llm_client参数保持为可选
                self.create_database_manager() # 传递正确的db_manager
            )
            self._registry.register_service("persona_updater", service)
            self._logger.info("创建人格更新器成功")
            return service
        except ImportError as e:
            self._logger.error(f"导入人格更新器失败: {e}", exc_info=True)
            raise ServiceError(f"创建人格更新器失败: {str(e)}")

    def get_persona_updater(self) -> Optional[IPersonaUpdater]:
        """获取已创建的人格更新器实例，如果不存在则创建"""
        cache_key = "persona_updater"
        
        # 如果已存在，直接返回
        if cache_key in self._service_cache:
            return self._service_cache[cache_key]
        
        # 如果不存在，创建新实例
        try:
            return self.create_persona_updater()
        except Exception as e:
            self._logger.error(f"获取人格更新器失败: {e}", exc_info=True)
            return None

    def get_service_registry(self) -> ServiceRegistry:
        """获取服务注册表"""
        return self._registry

    async def initialize_all_services(self) -> bool:
        """初始化所有服务"""
        self._logger.info("开始初始化所有服务")

        try:
            # 按依赖顺序创建服务
            self.create_database_manager()
            self.create_temporary_persona_updater() # 临时人格更新器需要优先创建
            self.create_message_collector()
            self.create_style_analyzer()
            self.create_quality_monitor()
            self.create_ml_analyzer()

            # 创建响应多样性管理器（在intelligent_responder之前）- 使用工厂方法
            try:
                self.create_response_diversity_manager() # 使用ServiceFactory的方法
            except Exception as e:
                self._logger.warning(f"创建响应多样性管理器失败（继续使用默认行为）: {e}")

            # 社交上下文注入器由 ComponentFactory 创建（plugin_lifecycle.py）

            self.create_intelligent_responder() # 重新启用智能回复器
            self.create_persona_manager()
            self.create_multidimensional_analyzer()
            self.create_progressive_learning()

            # Enable function-level monitoring when debug_mode is active.
            try:
                from ..services.monitoring.instrumentation import set_debug_mode
                set_debug_mode(self.config.debug_mode)
            except ImportError:
                if self.config.debug_mode:
                    self._logger.warning(
                        "prometheus_client 未安装，函数级性能监控不可用。"
                        "安装 prometheus_client 后重启即可启用。"
                    )

            # 启动所有注册的服务
            success = await self._registry.start_all_services()

            if success:
                self._logger.info("所有服务初始化成功")
            else:
                self._logger.error("部分服务初始化失败")

            return success
            
        except Exception as e:
            self._logger.error(f"服务初始化异常: {e}", exc_info=True)
            return False
    
    async def shutdown_all_services(self) -> bool:
        """关闭所有服务"""
        self._logger.info("开始关闭所有服务")
        
        try:
            success = await self._registry.stop_all_services()
            
            # 清理缓存
            self._service_cache.clear()
            
            if success:
                self._logger.info("所有服务关闭成功")
            else:
                self._logger.error("部分服务关闭失败")
            
            return success
            
        except Exception as e:
            self._logger.error(f"服务关闭异常: {e}", exc_info=True)
            return False
    
    def get_service_status(self) -> Dict[str, str]:
        """获取所有服务状态"""
        return self._registry.get_service_status()
    
    def clear_cache(self):
        """清理服务缓存"""
        self._service_cache.clear()
        self._logger.info("服务缓存已清理")

    @cached_service("response_diversity_manager")
    def create_response_diversity_manager(self):
        """创建响应多样性管理器"""
        try:
            from ..services.response import ResponseDiversityManager

            service = ResponseDiversityManager(
                config=self.config,
                db_manager=self.create_database_manager()
            )

            self._registry.register_service("response_diversity_manager", service)

            self._logger.info("创建响应多样性管理器成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入响应多样性管理器失败: {e}", exc_info=True)
            raise ServiceError(f"创建响应多样性管理器失败: {str(e)}")


# 将内部类移到模块顶层
class QQFilter:
    def __init__(self, target_qq_list, blacklist=None):
        self.target_qq_list = target_qq_list or []
        self.blacklist = blacklist or []
        self._logger = logger
    
    def should_collect_message(self, sender_id: str, group_id: str = None) -> bool:
        # 检查黑名单（支持个人QQ号和群聊格式）
        if self._is_in_blacklist(sender_id, group_id):
            return False
        
        # 如果没有指定目标列表，则学习所有非黑名单用户
        if not self.target_qq_list:
            return True
        
        # 检查是否在目标列表中（支持个人QQ号和群聊格式）
        return self._is_in_target_list(sender_id, group_id)
    
    def _is_in_blacklist(self, sender_id: str, group_id: str = None) -> bool:
        """检查用户是否在黑名单中"""
        if not self.blacklist:
            return False
        
        # 检查个人QQ号
        if sender_id in self.blacklist:
            return True
        
        # 检查群聊格式 (group_群号)
        if group_id:
            group_format = f"group_{group_id}"
            if group_format in self.blacklist:
                return True
        
        return False
    
    def _is_in_target_list(self, sender_id: str, group_id: str = None) -> bool:
        """检查用户是否在目标列表中"""
        # 检查个人QQ号
        if sender_id in self.target_qq_list:
            return True

        # 检查群聊格式 (group_群号)
        if group_id:
            group_format = f"group_{group_id}"
            if group_format in self.target_qq_list:
                return True

        return False

    def get_allowed_group_ids(self) -> list:
        """从 target_qq_list 中提取允许的群组 ID 列表。

        返回空列表表示不限制（允许所有群组）。
        """
        if not self.target_qq_list:
            return []

        prefix = "group_"
        return [
            item[len(prefix):]
            for item in self.target_qq_list
            if item.startswith(prefix)
        ]

    def get_blocked_group_ids(self) -> list:
        """从 target_blacklist 中提取需要排除的群组 ID 列表。"""
        if not self.blacklist:
            return []

        prefix = "group_"
        return [
            item[len(prefix):]
            for item in self.blacklist
            if item.startswith(prefix)
        ]


class MessageFilter:
    def __init__(self, config: PluginConfig, context: Context, prompts: Any = None):
        self.config = config
        self.context = context
        self.prompts = prompts # 保存 prompts
        self._logger = logger
    
    async def is_suitable_for_learning(self, message: str) -> bool:
        # 基础长度检查
        if len(message) < self.config.message_min_length:
            return False
        if len(message) > self.config.message_max_length:
            return False
        
        # 简单内容过滤
        if message.strip() in ['', '???', '。。。', '...']:
            return False
        
        # 使用 LLM 进行初步筛选
        try:
            current_persona = "默认人格"
            try:
                persona = await self.context.persona_manager.get_default_persona_v3()
                if persona:
                    current_persona = persona.get('prompt', '默认人格') if isinstance(persona, dict) else getattr(persona, 'prompt', '默认人格')
            except Exception:
                pass
            
            prompt = self.prompts.MESSAGE_FILTER_SUITABLE_FOR_LEARNING_PROMPT.format(
                current_persona=current_persona,
                message=message
            )
            
            # 不再使用LLM进行筛选，返回默认结果
            return False # 默认认为不适合学习
        except Exception as e:
            self._logger.error(f"LLM 筛选消息失败: {e}", exc_info=True)
            return False # LLM 调用失败，认为不适合


class LearningScheduler:
    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.is_running = False
        self._task = None
        self._logger = logger
    
    def start(self):
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._learning_loop())
            self._logger.info("学习调度器已启动")
    
    async def stop(self):
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._logger.info("学习调度器已停止")
    
    async def _learning_loop(self):
        while self.is_running:
            try:
                interval_seconds = self.plugin.plugin_config.learning_interval_hours * 3600 # 使用 plugin_config
                await asyncio.sleep(interval_seconds)
                
                if self.is_running and hasattr(self.plugin, '_perform_learning_cycle'):
                    await self.plugin._perform_learning_cycle()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"学习循环异常: {e}", exc_info=True)
                await asyncio.sleep(60) # 错误后等待1分钟再重试


class ComponentFactory:
    """组件工厂 - 创建轻量级组件"""
    
    def __init__(self, config: PluginConfig, service_factory: ServiceFactory):
        self.config = config
        self.service_factory = service_factory
        self._logger = logger
        # 添加服务缓存和注册表引用
        self._service_cache = service_factory._service_cache
        self._registry = service_factory._registry
    
    def create_qq_filter(self):
        """创建QQ号过滤器"""
        return QQFilter(self.config.target_qq_list, self.config.target_blacklist)
    
    def create_message_filter(self, context: Context):
        """创建消息过滤器"""
        prompts = self.service_factory.get_prompts() # 通过 service_factory 获取 prompts
        return MessageFilter(self.config, context, prompts)
    
    def create_learning_scheduler(self, plugin_instance):
        """创建学习调度器"""
        return LearningScheduler(plugin_instance)
    
    def create_persona_updater(self, context: Context, backup_manager):
        """创建人格更新器"""
        from ..services.persona import PersonaUpdater as ActualPersonaUpdater # 导入实际的 PersonaUpdater
        prompts = self.service_factory.get_prompts() # 获取 prompts
        return ActualPersonaUpdater(self.config, context, backup_manager, None, prompts)

    @cached_service("advanced_learning")
    def create_advanced_learning_service(self):
        """创建高级学习机制服务"""
        try:
            from ..services.core_learning import AdvancedLearningService

            service = AdvancedLearningService(
                self.config,
                database_manager=self.service_factory.create_database_manager(),
                persona_manager=self.service_factory.create_persona_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter() # 使用框架适配器
            )
            self._registry.register_service("advanced_learning", service)
            
            self._logger.info("创建高级学习服务成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入高级学习服务失败: {e}", exc_info=True)
            raise ServiceError(f"创建高级学习服务失败: {str(e)}")

    @cached_service("enhanced_interaction")
    def create_enhanced_interaction_service(self):
        """创建增强交互服务"""
        try:
            from ..services.state import EnhancedInteractionService

            service = EnhancedInteractionService(
                self.config,
                database_manager=self.service_factory.create_database_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter() # 使用框架适配器
            )
            self._registry.register_service("enhanced_interaction", service)
            
            self._logger.info("创建增强交互服务成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入增强交互服务失败: {e}", exc_info=True)
            raise ServiceError(f"创建增强交互服务失败: {str(e)}")

    @cached_service("intelligence_enhancement")
    def create_intelligence_enhancement_service(self):
        """创建智能化提升服务"""
        try:
            from ..services.analysis import IntelligenceEnhancementService

            service = IntelligenceEnhancementService(
                self.config,
                database_manager=self.service_factory.create_database_manager(),
                persona_manager=self.service_factory.create_persona_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter() # 使用框架适配器
            )
            self._registry.register_service("intelligence_enhancement", service)
            
            self._logger.info("创建智能化提升服务成功")
            return service
            
        except ImportError as e:
            self._logger.error(f"导入智能化提升服务失败: {e}", exc_info=True)
            raise ServiceError(f"创建智能化提升服务失败: {str(e)}")

    @cached_service("affection_manager")
    def create_affection_manager_service(self):
        """创建好感度管理服务 - 根据配置选择实现"""
        try:
            # 使用管理器工厂创建好感度管理器（根据配置选择实现）
            from ..services.database import get_manager_factory

            # 获取或创建管理器工厂
            manager_factory = get_manager_factory(self.config)

            # 创建好感度管理器
            service = manager_factory.create_affection_manager(
                database_manager=self.service_factory.create_database_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter()
            )

            self._registry.register_service("affection_manager", service)

            # 记录使用的实现类型
            impl_type = type(service).__name__
            self._logger.info(f"创建好感度管理服务成功 (实现: {impl_type})")
            return service

        except ImportError as e:
            self._logger.error(f"导入好感度管理服务失败: {e}", exc_info=True)
            raise ServiceError(f"创建好感度管理服务失败: {str(e)}")

    @cached_service("expression_pattern_learner")
    def create_expression_pattern_learner(self):
        """创建表达模式学习器"""
        try:
            from ..services.analysis import ExpressionPatternLearner

            # 使用单例模式获取实例
            service = ExpressionPatternLearner.get_instance(
                config=self.config,
                db_manager=self.service_factory.create_database_manager(),
                context=self.service_factory.context,
                llm_adapter=self.service_factory.create_framework_llm_adapter()
            )

            self._registry.register_service("expression_pattern_learner", service)

            self._logger.info("创建表达模式学习器成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入表达模式学习器失败: {e}", exc_info=True)
            raise ServiceError(f"创建表达模式学习器失败: {str(e)}")

    @cached_service("social_context_injector")
    def create_social_context_injector(self):
        """创建社交上下文注入器（整合了心理状态和行为指导功能）"""
        try:
            from ..services.social import SocialContextInjector
            from ..services.database import ManagerFactory

            db_manager = self.service_factory.create_database_manager()
            llm_adapter = self.service_factory.create_framework_llm_adapter()

            # 获取好感度管理器（如果已创建）
            affection_manager = self._service_cache.get("affection_manager")

            # 获取对话目标管理器（如果已创建）
            goal_manager = self._service_cache.get("conversation_goal_manager")

            # 创建心理状态管理器和社交关系管理器（整合自 PsychologicalSocialContextInjector）
            manager_factory = ManagerFactory(self.config)

            psychological_state_manager = None
            social_relation_manager = None

            try:
                # 创建心理状态管理器
                psychological_state_manager = manager_factory.create_psychological_manager(
                    database_manager=db_manager, # 使用正确的参数名 database_manager
                    llm_adapter=llm_adapter,
                    affection_manager=None # 避免循环依赖
                )

                # 创建社交关系管理器
                social_relation_manager = manager_factory.create_social_relation_manager(
                    database_manager=db_manager, # 使用正确的参数名 database_manager
                    llm_adapter=llm_adapter
                )

                self._logger.info(" 成功创建心理状态和社交关系管理器（整合到SocialContextInjector）")
            except Exception as e:
                self._logger.warning(f"创建心理状态/社交关系管理器失败: {e}，将使用基础功能")

            service = SocialContextInjector(
                database_manager=db_manager,
                affection_manager=affection_manager,
                mood_manager=affection_manager, # AffectionManager同时也管理情绪
                config=self.config, # 传递config以读取expression_patterns_hours配置
                psychological_state_manager=psychological_state_manager, # 新增：心理状态管理器
                social_relation_manager=social_relation_manager, # 新增：社交关系管理器（但使用原有实现）
                llm_adapter=llm_adapter, # 新增：LLM适配器
                goal_manager=goal_manager # 新增：对话目标管理器
            )

            self._registry.register_service("social_context_injector", service)

            if goal_manager:
                self._logger.info("创建社交上下文注入器成功（已整合心理状态功能和对话目标管理器）")
            else:
                self._logger.info("创建社交上下文注入器成功（已整合心理状态功能，对话目标管理器未初始化）")
            return service

        except ImportError as e:
            self._logger.error(f"导入社交上下文注入器失败: {e}", exc_info=True)
            raise ServiceError(f"创建社交上下文注入器失败: {str(e)}")

    @cached_service("conversation_goal_manager")
    def create_conversation_goal_manager(self):
        """创建对话目标管理器"""
        try:
            from ..services.quality import ConversationGoalManager

            service = ConversationGoalManager(
                database_manager=self.service_factory.create_database_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter(),
                config=self.config
            )

            self._registry.register_service("conversation_goal_manager", service)

            self._logger.info("创建对话目标管理器成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入对话目标管理器失败: {e}", exc_info=True)
            raise ServiceError(f"创建对话目标管理器失败: {str(e)}")

    @cached_service("intelligent_chat_service")
    def create_intelligent_chat_service(self):
        """创建智能对话服务"""
        try:
            from ..services.response import IntelligentChatService
            from ..services.database import ManagerFactory

            # 创建必要的依赖
            db_manager = self.service_factory.create_database_manager()
            llm_adapter = self.service_factory.create_framework_llm_adapter()

            # 创建对话目标管理器
            goal_manager = self.create_conversation_goal_manager()

            # 创建或获取社交上下文注入器，并设置goal_manager
            social_injector = self.create_social_context_injector()
            social_injector.goal_manager = goal_manager

            # 创建心理状态管理器（可选）
            psychological_state_manager = None
            try:
                manager_factory = ManagerFactory(self.config)
                psychological_state_manager = manager_factory.create_psychological_manager(
                    database_manager=db_manager,
                    llm_adapter=llm_adapter,
                    affection_manager=None
                )
                self._logger.info(" 为智能对话服务创建心理状态管理器成功")
            except Exception as e:
                self._logger.warning(f"创建心理状态管理器失败: {e}，智能对话服务将使用基础功能")

            # 创建服务实例
            service = IntelligentChatService(
                psychological_state_manager=psychological_state_manager,
                social_context_injector=social_injector,
                llm_adapter=llm_adapter,
                config=self.config
            )

            self._registry.register_service("intelligent_chat_service", service)

            self._logger.info("创建智能对话服务成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入智能对话服务失败: {e}", exc_info=True)
            raise ServiceError(f"创建智能对话服务失败: {str(e)}")

    @cached_service("metric_collector")
    def create_metric_collector(self):
        """创建性能指标收集器"""
        try:
            from ..services.monitoring import MetricCollector
            from ..utils.cache_manager import get_cache_manager

            service = MetricCollector(
                perf_tracker=self._service_cache.get("perf_collector"),
                cache_manager=get_cache_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter(),
                service_registry=self._registry,
                progressive_learning=self._service_cache.get("progressive_learning"),
            )
            self._registry.register_service("metric_collector", service)

            self._logger.info("创建性能指标收集器成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入性能指标收集器失败: {e}", exc_info=True)
            raise ServiceError(f"创建性能指标收集器失败: {str(e)}")

    @cached_service("health_checker")
    def create_health_checker(self):
        """创建健康检查器"""
        try:
            from ..services.monitoring import HealthChecker
            from ..utils.cache_manager import get_cache_manager

            service = HealthChecker(
                service_registry=self._registry,
                cache_manager=get_cache_manager(),
                llm_adapter=self.service_factory.create_framework_llm_adapter(),
            )

            self._logger.info("创建健康检查器成功")
            return service

        except ImportError as e:
            self._logger.error(f"导入健康检查器失败: {e}", exc_info=True)
            raise ServiceError(f"创建健康检查器失败: {str(e)}")


# 全局工厂实例管理器
class FactoryManager:
    """工厂管理器 - 单例模式管理所有工厂"""
    
    _instance = None
    _service_factory: Optional[ServiceFactory] = None
    _component_factory: Optional[ComponentFactory] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize_factories(self, config: PluginConfig, context: Context):
        """初始化工厂"""
        self._service_factory = ServiceFactory(config, context)
        self._component_factory = ComponentFactory(config, self._service_factory) # 注入 service_factory
    
    def get_service_factory(self) -> ServiceFactory:
        """获取服务工厂"""
        if self._service_factory is None:
            raise ServiceError("服务工厂未初始化")
        return self._service_factory
    
    def get_component_factory(self) -> ComponentFactory:
        """获取组件工厂"""
        if self._component_factory is None:
            raise ServiceError("组件工厂未初始化")
        return self._component_factory
    
    def get_service(self, service_name: str) -> Any:
        """
        通过名称获取已创建的服务实例。
        此方法委托给 ServiceFactory 的内部缓存。
        """
        if self._service_factory is None:
            raise ServiceError("服务工厂未初始化，无法获取服务")
        
        service = self._service_factory._service_cache.get(service_name)
        if service is None:
            raise ServiceError(f"服务 '{service_name}' 未找到或未初始化。请确保服务已通过 ServiceFactory 的 create_xxx 方法创建。")
        return service

    async def cleanup(self):
        """清理所有工厂"""
        if self._service_factory:
            await self._service_factory.shutdown_all_services()
            self._service_factory.clear_cache()
        
        self._service_factory = None
        self._component_factory = None
