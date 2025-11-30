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
                'confirmed_jargon': 0,
                'total_candidates': 0,
                'active_groups': 0,
                'total_occurrences': 0,
                'average_count': 0
            }

        try:
            # 调用数据库方法获取全局统计（不传chat_id）
            stats = await self.database_manager.get_jargon_statistics(chat_id=None)

            # 数据库返回的字段：total_candidates, confirmed_jargon, completed_inference, total_occurrences, average_count, active_groups
            # WebUI需要的字段：total_jargons, confirmed_jargon, total_candidates, active_groups, ...
            return {
                'total_jargons': stats.get('total_candidates', 0),  # 总候选数即总黑话数
                'confirmed_jargon': stats.get('confirmed_jargon', 0),  # 已确认的黑话
                'total_candidates': stats.get('total_candidates', 0),  # 总候选数
                'active_groups': stats.get('active_groups', 0),  # 活跃群组数
                'total_occurrences': stats.get('total_occurrences', 0),  # 总出现次数
                'average_count': stats.get('average_count', 0),  # 平均出现次数
                'completed_inference': stats.get('completed_inference', 0)  # 已完成推理的数量
            }
        except Exception as e:
            logger.error(f"获取黑话统计失败: {e}", exc_info=True)
            return {
                'total_jargons': 0,
                'confirmed_jargon': 0,
                'total_candidates': 0,
                'active_groups': 0,
                'total_occurrences': 0,
                'average_count': 0
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
            # 使用数据库的 get_recent_jargon_list 方法
            # 注意：原方法不支持分页，这里需要手动处理
            jargons = await self.database_manager.get_recent_jargon_list(
                chat_id=group_id,
                limit=page_size * page,  # 获取到当前页的所有数据
                only_confirmed=False  # 获取所有黑话，包括候选
            )

            # 手动实现分页
            total = len(jargons)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_jargons = jargons[start_idx:end_idx] if start_idx < len(jargons) else []

            # 格式化数据
            formatted_jargons = []
            for j in page_jargons:
                formatted_jargons.append({
                    'id': j.get('id'),
                    'content': j.get('content'),
                    'meaning': j.get('meaning', ''),
                    'is_jargon': bool(j.get('is_jargon', False)),
                    'is_global': bool(j.get('is_global', False)),
                    'count': j.get('count', 0),
                    'chat_id': j.get('chat_id'),
                    'updated_at': j.get('updated_at')
                })

            return {
                'jargons': formatted_jargons,
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
            # 使用 delete_jargon_by_id 方法
            success = await self.database_manager.delete_jargon_by_id(jargon_id)
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
