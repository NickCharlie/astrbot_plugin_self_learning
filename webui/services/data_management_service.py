"""
数据管理服务 — 各功能模块数据统计与清空
"""
from typing import Dict, Any, Tuple

from astrbot.api import logger


class DataManagementService:
    """数据管理服务"""

    def __init__(self, container):
        self.container = container
        self.database_manager = container.database_manager

    def _check_db(self):
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

    async def get_data_statistics(self) -> Dict[str, int]:
        """获取各功能模块数据统计"""
        self._check_db()
        return await self.database_manager.get_data_statistics()

    async def clear_messages(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_messages_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 消息数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条消息数据", deleted
        return False, "清除消息数据失败", 0

    async def clear_persona_reviews(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_persona_reviews_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 人格审查数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条人格审查数据", deleted
        return False, "清除人格审查数据失败", 0

    async def clear_style_learning(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_style_learning_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 风格学习数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条风格学习数据", deleted
        return False, "清除风格学习数据失败", 0

    async def clear_jargon(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_jargon_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 黑话数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条黑话数据", deleted
        return False, "清除黑话数据失败", 0

    async def clear_learning_history(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_learning_history_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 学习历史数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条学习历史数据", deleted
        return False, "清除学习历史数据失败", 0

    async def clear_all(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_all_plugin_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 全部数据已清除，共 {deleted} 行")
            return True, f"已清除全部 {deleted} 条数据", deleted
        return False, "清除全部数据失败（部分可能已清除）", deleted
