"""
黑话管理服务 - 处理黑话学习相关业务逻辑
"""
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger


class JargonService:
    """黑话管理服务"""

    def __init__(self, container):
        """
        初始化黑话管理服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.database_manager = container.database_manager

    async def get_jargon_stats(self) -> Dict[str, Any]:
        """
        获取黑话统计信息

        Returns:
            Dict: 统计信息
        """
        if not self.database_manager:
            return {
                'total_jargons': 0,
                'global_jargons': 0,
                'group_specific_jargons': 0,
                'total_groups': 0
            }

        try:
            stats = await self.database_manager.get_jargon_statistics()
            return stats if stats else {
                'total_jargons': 0,
                'global_jargons': 0,
                'group_specific_jargons': 0,
                'total_groups': 0
            }
        except Exception as e:
            logger.error(f"获取黑话统计失败: {e}", exc_info=True)
            return {
                'total_jargons': 0,
                'global_jargons': 0,
                'group_specific_jargons': 0,
                'total_groups': 0
            }

    async def get_jargon_list(
        self,
        group_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        获取黑话列表

        Args:
            group_id: 群组ID (可选,默认获取全局黑话)
            page: 页码
            page_size: 每页数量

        Returns:
            Dict: 黑话列表和分页信息
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            jargons, total = await self.database_manager.get_jargon_list(
                group_id=group_id,
                offset=(page - 1) * page_size,
                limit=page_size
            )

            return {
                'jargons': jargons,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        except Exception as e:
            logger.error(f"获取黑话列表失败: {e}", exc_info=True)
            raise

    async def search_jargon(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索黑话

        Args:
            keyword: 搜索关键词

        Returns:
            List[Dict]: 匹配的黑话列表
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            results = await self.database_manager.search_jargon(keyword)
            return results
        except Exception as e:
            logger.error(f"搜索黑话失败: {e}", exc_info=True)
            raise

    async def delete_jargon(self, jargon_id: int) -> Tuple[bool, str]:
        """
        删除黑话

        Args:
            jargon_id: 黑话ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            success = await self.database_manager.delete_jargon(jargon_id)
            if success:
                logger.info(f"黑话 {jargon_id} 已删除")
                return True, f"黑话 {jargon_id} 已删除"
            else:
                return False, "删除失败"
        except Exception as e:
            logger.error(f"删除黑话失败: {e}", exc_info=True)
            raise

    async def toggle_jargon_global(self, jargon_id: int) -> Tuple[bool, str, bool]:
        """
        切换黑话的全局状态

        Args:
            jargon_id: 黑话ID

        Returns:
            Tuple[bool, str, bool]: (是否成功, 消息, 新的全局状态)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            # 获取当前状态
            jargon = await self.database_manager.get_jargon_by_id(jargon_id)
            if not jargon:
                return False, "黑话不存在", False

            new_status = not jargon.get('is_global', False)
            success = await self.database_manager.set_jargon_global(jargon_id, new_status)

            if success:
                status_text = "全局" if new_status else "非全局"
                logger.info(f"黑话 {jargon_id} 已设置为{status_text}")
                return True, f"黑话已设置为{status_text}", new_status
            else:
                return False, "设置失败", jargon.get('is_global', False)
        except Exception as e:
            logger.error(f"切换黑话全局状态失败: {e}", exc_info=True)
            raise

    async def get_jargon_groups(self) -> List[str]:
        """
        获取包含黑话的群组列表

        Returns:
            List[str]: 群组ID列表
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            groups = await self.database_manager.get_jargon_groups()
            return groups
        except Exception as e:
            logger.error(f"获取黑话群组列表失败: {e}", exc_info=True)
            raise

    async def sync_global_to_group(self, target_group_id: str) -> Tuple[bool, str, int]:
        """
        同步全局黑话到指定群组

        Args:
            target_group_id: 目标群组ID

        Returns:
            Tuple[bool, str, int]: (是否成功, 消息, 同步数量)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            count = await self.database_manager.sync_global_jargon_to_group(target_group_id)
            logger.info(f"已同步 {count} 个全局黑话到群组 {target_group_id}")
            return True, f"已同步 {count} 个全局黑话", count
        except Exception as e:
            logger.error(f"同步全局黑话失败: {e}", exc_info=True)
            raise
