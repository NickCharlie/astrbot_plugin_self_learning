"""
统一管理器工厂
根据配置自动创建增强型或原始管理器
"""
from typing import Optional, Union
from astrbot.api import logger

from ...config import PluginConfig
from ...core.interfaces import IDataStorage
from ...core.framework_llm_adapter import FrameworkLLMAdapter


class ManagerFactory:
    """
    管理器工厂 - 根据配置创建合适的管理器实现

    用法:
        factory = ManagerFactory(config)

        # 创建数据库管理器
        db_manager = factory.create_database_manager(context)

        # 创建好感度管理器
        affection_mgr = factory.create_affection_manager(db_manager, llm_adapter)

        # 创建记忆管理器
        memory_mgr = factory.create_memory_manager(db_manager, llm_adapter)

        # 创建心理状态管理器
        state_mgr = factory.create_psychological_manager(db_manager, llm_adapter)
    """

    def __init__(self, config: PluginConfig):
        """
        初始化管理器工厂

        Args:
            config: 插件配置
        """
        self.config = config
        logger.info("[ManagerFactory] initialized")

    # 数据库管理器

    def create_database_manager(self, context=None):
        """
        创建数据库管理器

        Args:
            context: 上下文对象

        Returns:
            SQLAlchemy 数据库管理器实例
        """
        from .sqlalchemy_database_manager import SQLAlchemyDatabaseManager
        logger.info("[ManagerFactory] Creating SQLAlchemy database manager")
        return SQLAlchemyDatabaseManager(self.config, context)

    # 好感度管理器

    def create_affection_manager(
        self,
        database_manager: IDataStorage,
        llm_adapter: Optional[FrameworkLLMAdapter] = None
    ):
        """
        创建好感度管理器

        Args:
            database_manager: 数据库管理器
            llm_adapter: LLM 适配器

        Returns:
            好感度管理器实例
        """
        from ..state import AffectionManager
        logger.info("[ManagerFactory] Creating affection manager")
        return AffectionManager(self.config, database_manager, llm_adapter)

    # 记忆管理器

    def create_memory_manager(
        self,
        database_manager: IDataStorage,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        decay_manager=None
    ):
        """
        创建记忆图管理器

        Args:
            database_manager: 数据库管理器
            llm_adapter: LLM 适配器
            decay_manager: 时间衰减管理器

        Returns:
            记忆管理器实例（原始或增强型）
        """
        from ..state import EnhancedMemoryGraphManager
        logger.info("[ManagerFactory] Creating memory graph manager")
        return EnhancedMemoryGraphManager.get_instance(
            self.config,
            database_manager,
            llm_adapter,
            decay_manager
        )

    # 心理状态管理器

    def create_psychological_manager(
        self,
        database_manager: IDataStorage,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        affection_manager=None
    ):
        """
        创建心理状态管理器

        Args:
            database_manager: 数据库管理器
            llm_adapter: LLM 适配器
            affection_manager: 好感度管理器

        Returns:
            心理状态管理器实例（原始或增强型）
        """
        from ..state import EnhancedPsychologicalStateManager
        logger.info("[ManagerFactory] Creating psychological state manager")
        return EnhancedPsychologicalStateManager(
            self.config,
            database_manager,
            llm_adapter,
            affection_manager
        )

    # 社交关系管理器

    def create_social_relation_manager(
        self,
        database_manager: IDataStorage,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        psychological_manager=None
    ):
        """
        创建社交关系管理器

        Args:
            database_manager: 数据库管理器
            llm_adapter: LLM 适配器
            psychological_manager: 心理状态管理器

        Returns:
            社交关系管理器实例
        """
        # 注意: 原始的社交关系管理器已经叫 EnhancedSocialRelationManager
        # 所以这里不需要区分
        from ..social import EnhancedSocialRelationManager
        logger.info(" [工厂] 创建社交关系管理器")
        return EnhancedSocialRelationManager(
            self.config,
            database_manager,
            llm_adapter,
            psychological_manager
        )

    # 其他管理器（可根据需要扩展）

    def create_diversity_manager(
        self,
        database_manager: IDataStorage,
        llm_adapter: Optional[FrameworkLLMAdapter] = None
    ):
        """创建响应多样性管理器"""
        from ..response import ResponseDiversityManager
        logger.info(" [工厂] 创建响应多样性管理器")
        return ResponseDiversityManager(self.config, database_manager, llm_adapter)

    def create_time_decay_manager(
        self,
        database_manager: IDataStorage
    ):
        """创建时间衰减管理器"""
        from ..state import TimeDecayManager
        logger.info(" [工厂] 创建时间衰减管理器")
        return TimeDecayManager(self.config, database_manager)

    # 批量创建

    def create_all_managers(self, context=None) -> dict:
        """
        创建所有管理器

        Args:
            context: 上下文对象

        Returns:
            dict: 包含所有管理器的字典
        """
        logger.info("=" * 70)
        logger.info(" [管理器工厂] 开始创建所有管理器...")
        logger.info("=" * 70)

        managers = {}

        # 1. 数据库管理器
        managers['database'] = self.create_database_manager(context)

        # 2. LLM 适配器（从主插件获取）
        managers['llm_adapter'] = None # 需要外部传入

        # 3. 时间衰减管理器
        managers['time_decay'] = self.create_time_decay_manager(managers['database'])

        # 4. 好感度管理器
        managers['affection'] = self.create_affection_manager(
            managers['database'],
            managers['llm_adapter']
        )

        # 5. 心理状态管理器
        managers['psychological'] = self.create_psychological_manager(
            managers['database'],
            managers['llm_adapter'],
            managers['affection']
        )

        # 6. 社交关系管理器
        managers['social_relation'] = self.create_social_relation_manager(
            managers['database'],
            managers['llm_adapter'],
            managers['psychological']
        )

        # 7. 记忆管理器
        managers['memory'] = self.create_memory_manager(
            managers['database'],
            managers['llm_adapter'],
            managers['time_decay']
        )

        # 8. 响应多样性管理器
        managers['diversity'] = self.create_diversity_manager(
            managers['database'],
            managers['llm_adapter']
        )

        logger.info("=" * 70)
        logger.info(f" [管理器工厂] 成功创建 {len(managers)} 个管理器")
        logger.info("=" * 70)

        return managers

    # 工具方法

    def get_configuration_info(self) -> dict:
        """
        获取配置信息

        Returns:
            dict: 配置信息
        """
        return {
            'enable_affection_system': self.config.enable_affection_system,
            'enable_memory_graph': self.config.enable_memory_graph,
            'enable_maibot_features': self.config.enable_maibot_features,
        }

    def print_configuration(self):
        """打印当前配置"""
        info = self.get_configuration_info()

        logger.info("=" * 70)
        logger.info(" [管理器工厂] 当前配置:")
        logger.info("=" * 70)

        for key, value in info.items():
            status = " 启用" if value else " 禁用"
            logger.info(f" {key}: {status}")

        logger.info("=" * 70)


# 全局工厂实例

_global_factory = None


def get_manager_factory(config: PluginConfig = None) -> ManagerFactory:
    """
    获取全局管理器工厂单例

    Args:
        config: 插件配置（首次调用时必须提供）

    Returns:
        ManagerFactory: 管理器工厂实例
    """
    global _global_factory

    if _global_factory is None:
        if config is None:
            raise ValueError("首次调用 get_manager_factory 必须提供 config 参数")
        _global_factory = ManagerFactory(config)

    return _global_factory


__all__ = [
    'ManagerFactory',
    'get_manager_factory',
]
