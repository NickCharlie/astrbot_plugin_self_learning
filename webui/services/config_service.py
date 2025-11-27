"""
配置服务 - 处理插件配置相关业务逻辑
"""
from dataclasses import asdict
from typing import Dict, Any, Tuple
from astrbot.api import logger


class ConfigService:
    """配置服务"""

    def __init__(self, container):
        """
        初始化配置服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.plugin_config = container.plugin_config

    async def get_config(self) -> Dict[str, Any]:
        """
        获取插件配置

        Returns:
            Dict: 插件配置字典
        """
        if self.plugin_config:
            return asdict(self.plugin_config)
        else:
            raise ValueError("Plugin config not initialized")

    async def update_config(self, new_config: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        更新插件配置

        Args:
            new_config: 新的配置数据

        Returns:
            Tuple[bool, str, Dict]: (是否成功, 消息, 更新后的配置)
        """
        if not self.plugin_config:
            raise ValueError("Plugin config not initialized")

        # 更新配置
        for key, value in new_config.items():
            if hasattr(self.plugin_config, key):
                setattr(self.plugin_config, key, value)
                logger.info(f"配置项 {key} 已更新为: {value}")
            else:
                logger.warning(f"配置项 {key} 不存在，跳过")

        # TODO: 保存配置到文件
        # 需要实现配置持久化逻辑

        return True, "Config updated successfully", asdict(self.plugin_config)
