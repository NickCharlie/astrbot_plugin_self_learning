"""
黑话管理服务 - 处理黑话学习相关业务逻辑
"""
import json
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

    @staticmethod
    def _format_jargon_for_frontend(j: Dict[str, Any]) -> Dict[str, Any]:
        """
        将数据库字段映射为前端期望的字段名

        DB → Frontend:
            content → term
            is_jargon → is_confirmed
            count → occurrences
            raw_content (JSON str) → context_examples (list)
            chat_id → group_id
        """
        # 解析 raw_content JSON 为 context_examples 列表
        raw = j.get('raw_content', '[]')
        try:
            context_examples = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            context_examples = []

        return {
            'id': j.get('id'),
            'term': j.get('content', ''),
            'meaning': j.get('meaning', ''),
            'is_confirmed': bool(j.get('is_jargon', False)),
            'is_global': bool(j.get('is_global', False)),
            'occurrences': j.get('count', 0),
            'group_id': j.get('chat_id'),
            'context_examples': context_examples,
            'updated_at': j.get('updated_at'),
        }

    async def get_jargon_stats(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取黑话统计信息

        Args:
            group_id: 群组ID（可选，None 表示全局统计）

        Returns:
            Dict: 统计信息（字段已与前端对齐）
        """
        empty = {
            'total_candidates': 0,
            'confirmed_jargon': 0,
            'completed_inference': 0,
            'total_occurrences': 0,
            'average_count': 0,
            'active_groups': 0,
        }
        if not self.database_manager:
            return empty

        try:
            stats = await self.database_manager.get_jargon_statistics(
                group_id=group_id
            )
            return {
                'total_candidates': stats.get('total_candidates', 0),
                'confirmed_jargon': stats.get('confirmed_jargon', 0),
                'completed_inference': stats.get('completed_inference', 0),
                'total_occurrences': stats.get('total_occurrences', 0),
                'average_count': stats.get('average_count', 0),
                'active_groups': stats.get('active_groups', 0),
            }
        except Exception as e:
            logger.error(f"获取黑话统计失败: {e}", exc_info=True)
            return empty

    async def get_jargon_list(
        self,
        group_id: Optional[str] = None,
        confirmed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        获取黑话列表

        Args:
            group_id: 群组ID (可选,默认获取全局黑话)
            confirmed: 过滤已确认/未确认（None=全部）
            page: 页码
            page_size: 每页数量

        Returns:
            Dict: 黑话列表和分页信息，key 为 'jargon_list'
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            jargons = await self.database_manager.get_recent_jargon_list(
                chat_id=group_id,
                limit=page_size * page,
                only_confirmed=confirmed,
            )

            # 手动实现分页
            total = len(jargons)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_jargons = jargons[start_idx:end_idx] if start_idx < total else []

            formatted = [self._format_jargon_for_frontend(j) for j in page_jargons]

            return {
                'jargon_list': formatted,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        except Exception as e:
            logger.error(f"获取黑话列表失败: {e}", exc_info=True)
            raise

    async def search_jargon(
        self,
        keyword: str,
        chat_id: Optional[str] = None,
        confirmed_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        搜索黑话

        Args:
            keyword: 搜索关键词
            chat_id: 群组ID（可选）
            confirmed_only: 是否仅返回已确认的黑话

        Returns:
            List[Dict]: 匹配的黑话列表（字段已映射为前端格式）
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            results = await self.database_manager.search_jargon(
                keyword, chat_id=chat_id
            )
            # 按 confirmed_only 过滤
            if confirmed_only:
                results = [r for r in results if r.get('is_jargon')]

            return [self._format_jargon_for_frontend(r) for r in results]
        except Exception as e:
            logger.error(f"搜索黑话失败: {e}", exc_info=True)
            raise

    async def get_global_jargon_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取全局共享的黑话列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Dict]: 全局黑话列表（字段已映射为前端格式）
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            jargons = await self.database_manager.get_global_jargon_list(limit=limit)
            return [self._format_jargon_for_frontend(j) for j in jargons]
        except Exception as e:
            logger.error(f"获取全局黑话列表失败: {e}", exc_info=True)
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
