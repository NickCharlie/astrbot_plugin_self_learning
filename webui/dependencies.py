"""
依赖注入容器 - 管理全局服务实例
"""
from typing import Optional, Any, List, Dict
from astrbot.api import logger


class ServiceContainer:
    """服务容器 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 插件配置
        self.plugin_config: Optional[Any] = None

        # 核心服务
        self.persona_manager: Optional[Any] = None
        self.persona_updater: Optional[Any] = None
        self.database_manager: Optional[Any] = None
        self.llm_adapter: Optional[Any] = None
        self.progressive_learning: Optional[Any] = None
        self.factory_manager: Optional[Any] = None

        # AstrBot 框架服务
        self.astrbot_persona_manager: Optional[Any] = None

        # PersonaWebManager 实例
        self.persona_web_manager: Optional[Any] = None

        # WebUI 配置
        self.webui_config: Optional[Any] = None

        # 密码配置
        self.password_config: Dict[str, Any] = {}

        # 待审核更新
        self.pending_updates: List[Any] = []

        # group_id到unified_msg_origin映射表（多配置文件支持）
        self.group_id_to_unified_origin: Dict[str, str] = {}

        # 智能指标服务
        self.intelligence_metrics_service: Optional[Any] = None

        # 性能计时收集器（指向插件实例的 get_perf_data 方法）
        self.perf_collector: Optional[Any] = None

        self._initialized = True

    def initialize(
        self,
        plugin_config,
        factory_manager,
        llm_client=None,
        astrbot_persona_manager=None,
        group_id_to_unified_origin=None
    ):
        """
        初始化服务容器

        Args:
            plugin_config: 插件配置
            factory_manager: 工厂管理器
            llm_client: LLM 客户端（废弃，保留兼容性）
            astrbot_persona_manager: AstrBot 人格管理器
            group_id_to_unified_origin: group_id到unified_msg_origin映射表
        """
        self.plugin_config = plugin_config
        self.factory_manager = factory_manager
        self.astrbot_persona_manager = astrbot_persona_manager
        if group_id_to_unified_origin is not None:
            self.group_id_to_unified_origin = group_id_to_unified_origin

        # 从工厂获取服务
        service_factory = factory_manager.get_service_factory()
        self.persona_manager = service_factory.create_persona_manager()
        self.database_manager = service_factory.create_database_manager()
        self.llm_adapter = service_factory.create_framework_llm_adapter()
        self.progressive_learning = service_factory.create_progressive_learning()

        # 获取人格更新器
        try:
            self.persona_updater = service_factory.get_persona_updater()
            logger.info(f" [WebUI] persona_updater 获取成功: {type(self.persona_updater)}")
        except Exception as e:
            logger.warning(f"获取 persona_updater 失败: {e}")
            self.persona_updater = None

        # 创建 WebUI 配置
        from .config import WebUIConfig
        self.webui_config = WebUIConfig.from_plugin_config(plugin_config)

        # 初始化智能指标服务
        try:
            from ..services.analysis import IntelligenceMetricsService
            self.intelligence_metrics_service = IntelligenceMetricsService(
                plugin_config,
                self.database_manager,
                llm_adapter=self.llm_adapter
            )
        except Exception as e:
            logger.warning(f"初始化智能指标服务失败: {e}")

        # 初始化 PersonaWebManager
        if astrbot_persona_manager:
            try:
                from ..persona_web_manager import PersonaWebManager
                self.persona_web_manager = PersonaWebManager(astrbot_persona_manager)
                # 传递 group_id_to_unified_origin 映射引用（多配置文件支持）
                self.persona_web_manager.group_id_to_unified_origin = self.group_id_to_unified_origin
                logger.info(" [WebUI] PersonaWebManager 初始化成功")
            except Exception as e:
                logger.warning(f"初始化 PersonaWebManager 失败: {e}")
                self.persona_web_manager = None
        else:
            logger.warning("astrbot_persona_manager 未提供，无法初始化 PersonaWebManager")
            self.persona_web_manager = None

        logger.info(" [WebUI] 服务容器初始化完成")

    def get_plugin_config(self):
        """获取插件配置"""
        return self.plugin_config

    def get_database_manager(self):
        """获取数据库管理器"""
        return self.database_manager

    def get_llm_adapter(self):
        """获取 LLM 适配器"""
        return self.llm_adapter

    def get_persona_manager(self):
        """获取人格管理器"""
        return self.persona_manager


# 全局容器实例
_container = ServiceContainer()


def get_container() -> ServiceContainer:
    """获取全局服务容器"""
    return _container


# 兼容原有的 set_plugin_services 接口

async def set_plugin_services(
    plugin_config,
    factory_manager,
    llm_client,
    astrbot_persona_manager,
    group_id_to_unified_origin=None
):
    """
    设置插件服务（兼容原有接口）

    Args:
        plugin_config: 插件配置
        factory_manager: 工厂管理器
        llm_client: LLM 客户端（废弃）
        astrbot_persona_manager: AstrBot 人格管理器
        group_id_to_unified_origin: group_id到unified_msg_origin映射表
    """
    _container.initialize(
        plugin_config=plugin_config,
        factory_manager=factory_manager,
        llm_client=llm_client,
        astrbot_persona_manager=astrbot_persona_manager,
        group_id_to_unified_origin=group_id_to_unified_origin
    )

    logger.info(" [WebUI] 插件服务设置完成")
