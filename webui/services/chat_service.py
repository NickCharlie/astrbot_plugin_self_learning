"""
聊天历史服务 - 处理聊天历史相关业务逻辑
"""
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger


class ChatService:
    """聊天历史服务"""

    def __init__(self, container):
        """
        初始化聊天历史服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.database_manager = container.database_manager

    async def get_chat_history(
        self,
        group_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取聊天历史记录

        Args:
            group_id: 群组ID (可选)
            start_time: 开始时间戳 (可选)
            end_time: 结束时间戳 (可选)
            limit: 返回数量限制

        Returns:
            List[Dict]: 聊天记录列表
        """
        if not self.database_manager:
            return []

        try:
            history = await self.database_manager.get_chat_history(
                group_id=group_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            return history if history else []
        except Exception as e:
            logger.error(f"获取聊天历史失败: {e}", exc_info=True)
            return []

    async def get_chat_message_detail(self, message_id: int) -> Optional[Dict[str, Any]]:
        """
        获取聊天消息详情

        Args:
            message_id: 消息ID

        Returns:
            Optional[Dict]: 消息详情
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            message = await self.database_manager.get_message_by_id(message_id)
            return message
        except Exception as e:
            logger.error(f"获取消息详情失败: {e}", exc_info=True)
            raise

    async def delete_chat_message(self, message_id: int) -> Tuple[bool, str]:
        """
        删除聊天消息

        Args:
            message_id: 消息ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            success = await self.database_manager.delete_message(message_id)
            if success:
                logger.info(f"消息 {message_id} 已删除")
                return True, f"消息 {message_id} 已删除"
            else:
                return False, "删除失败"
        except Exception as e:
            logger.error(f"删除消息失败: {e}", exc_info=True)
            raise

    async def get_chat_statistics(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取聊天统计信息

        Args:
            group_id: 群组ID (可选)

        Returns:
            Dict: 统计信息
        """
        if not self.database_manager:
            return {
                'total_messages': 0,
                'total_users': 0,
                'date_range': None
            }

        try:
            stats = await self.database_manager.get_chat_statistics(group_id)
            return stats if stats else {
                'total_messages': 0,
                'total_users': 0,
                'date_range': None
            }
        except Exception as e:
            logger.error(f"获取聊天统计失败: {e}", exc_info=True)
            return {
                'total_messages': 0,
                'total_users': 0,
                'date_range': None
            }
