"""
社交关系服务 - 处理社交关系分析相关业务逻辑
"""
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger


class SocialService:
    """社交关系服务"""

    def __init__(self, container):
        """
        初始化社交关系服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.factory_manager = container.factory_manager

    async def get_social_relations(self, group_id: str) -> Dict[str, Any]:
        """
        获取指定群组的社交关系分析数据

        Args:
            group_id: 群组ID

        Returns:
            Dict: 社交关系数据
        """
        try:
            if not self.factory_manager:
                return {
                    "group_id": group_id,
                    "relations": [],
                    "members": [],
                    "error": "工厂管理器未初始化"
                }

            # 获取社交关系管理器
            social_manager = self.factory_manager.get_social_relation_manager()
            if not social_manager:
                return {
                    "group_id": group_id,
                    "relations": [],
                    "members": [],
                    "error": "社交关系管理器未初始化"
                }

            # 获取社交关系数据
            relations_data = await social_manager.get_social_relations(group_id)

            return {
                "group_id": group_id,
                "relations": relations_data.get("relations", []),
                "members": relations_data.get("members", []),
                "metadata": relations_data.get("metadata", {})
            }

        except Exception as e:
            logger.error(f"获取社交关系失败: {e}", exc_info=True)
            return {
                "group_id": group_id,
                "relations": [],
                "members": [],
                "error": str(e)
            }

    async def get_available_groups(self) -> List[str]:
        """
        获取可用于社交关系分析的群组列表

        Returns:
            List[str]: 群组ID列表
        """
        try:
            if not self.factory_manager:
                return []

            social_manager = self.factory_manager.get_social_relation_manager()
            if not social_manager:
                return []

            groups = await social_manager.get_available_groups()
            return groups if groups else []

        except Exception as e:
            logger.error(f"获取可用群组列表失败: {e}", exc_info=True)
            return []

    async def trigger_analysis(self, group_id: str) -> Tuple[bool, str]:
        """
        触发群组社交关系分析

        Args:
            group_id: 群组ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            if not self.factory_manager:
                return False, "工厂管理器未初始化"

            social_manager = self.factory_manager.get_social_relation_manager()
            if not social_manager:
                return False, "社交关系管理器未初始化"

            # 触发分析
            success = await social_manager.analyze_social_relations(group_id)

            if success:
                logger.info(f"群组 {group_id} 的社交关系分析已触发")
                return True, f"群组 {group_id} 的社交关系分析已开始"
            else:
                return False, "触发分析失败"

        except Exception as e:
            logger.error(f"触发社交关系分析失败: {e}", exc_info=True)
            return False, f"触发分析失败: {str(e)}"

    async def clear_relations(self, group_id: str) -> Tuple[bool, str]:
        """
        清空群组社交关系数据

        Args:
            group_id: 群组ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            if not self.factory_manager:
                return False, "工厂管理器未初始化"

            social_manager = self.factory_manager.get_social_relation_manager()
            if not social_manager:
                return False, "社交关系管理器未初始化"

            # 清空数据
            success = await social_manager.clear_social_relations(group_id)

            if success:
                logger.info(f"群组 {group_id} 的社交关系数据已清空")
                return True, f"群组 {group_id} 的社交关系数据已清空"
            else:
                return False, "清空数据失败"

        except Exception as e:
            logger.error(f"清空社交关系数据失败: {e}", exc_info=True)
            return False, f"清空数据失败: {str(e)}"

    async def get_user_relations(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """
        获取指定用户的社交关系

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            Dict: 用户社交关系数据
        """
        try:
            if not self.factory_manager:
                return {
                    "user_id": user_id,
                    "relations": [],
                    "error": "工厂管理器未初始化"
                }

            social_manager = self.factory_manager.get_social_relation_manager()
            if not social_manager:
                return {
                    "user_id": user_id,
                    "relations": [],
                    "error": "社交关系管理器未初始化"
                }

            # 获取用户社交关系
            user_relations = await social_manager.get_user_relations(group_id, user_id)

            return {
                "user_id": user_id,
                "group_id": group_id,
                "relations": user_relations.get("relations", []),
                "profile": user_relations.get("profile", {})
            }

        except Exception as e:
            logger.error(f"获取用户社交关系失败: {e}", exc_info=True)
            return {
                "user_id": user_id,
                "relations": [],
                "error": str(e)
            }
