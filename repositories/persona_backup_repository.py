"""
人格备份 Repository — PersonaBackup 表的数据访问
"""
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, delete
from typing import List, Optional, Dict, Any

from astrbot.api import logger
from .base_repository import BaseRepository
from ..models.orm.psychological import PersonaBackup


class PersonaBackupRepository(BaseRepository[PersonaBackup]):
    """人格备份 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PersonaBackup)

    async def create_backup(
        self,
        backup_data: Dict[str, Any]
    ) -> Optional[PersonaBackup]:
        """
        创建人格备份

        Args:
            backup_data: 备份字段字典，至少包含 backup_name

        Returns:
            Optional[PersonaBackup]: 创建的记录
        """
        try:
            backup_data.setdefault('timestamp', time.time())
            return await self.create(**backup_data)
        except Exception as e:
            logger.error(f"[PersonaBackupRepository] 创建备份失败: {e}")
            return None

    async def list_backups(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[PersonaBackup]:
        """
        列出所有备份（按时间倒序）

        Args:
            limit: 最大返回数量
            offset: 偏移量

        Returns:
            List[PersonaBackup]: 备份列表
        """
        try:
            stmt = (
                select(PersonaBackup)
                .order_by(desc(PersonaBackup.timestamp))
                .offset(offset)
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"[PersonaBackupRepository] 列出备份失败: {e}")
            return []

    async def get_backup(self, backup_id: int) -> Optional[PersonaBackup]:
        """
        获取指定备份

        Args:
            backup_id: 备份 ID

        Returns:
            Optional[PersonaBackup]: 备份对象
        """
        return await self.get_by_id(backup_id)

    async def get_by_name(self, backup_name: str) -> Optional[PersonaBackup]:
        """
        按名称获取最近的备份

        Args:
            backup_name: 备份名称

        Returns:
            Optional[PersonaBackup]: 备份对象
        """
        try:
            stmt = (
                select(PersonaBackup)
                .where(PersonaBackup.backup_name == backup_name)
                .order_by(desc(PersonaBackup.timestamp))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[PersonaBackupRepository] 按名称获取备份失败: {e}")
            return None

    async def delete_backup(self, backup_id: int) -> bool:
        """
        删除指定备份

        Args:
            backup_id: 备份 ID

        Returns:
            bool: 是否成功
        """
        return await self.delete_by_id(backup_id)

    async def count_backups(self) -> int:
        """
        统计备份总数

        Returns:
            int: 备份数量
        """
        try:
            stmt = select(func.count()).select_from(PersonaBackup)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"[PersonaBackupRepository] 统计备份失败: {e}")
            return 0

    async def delete_oldest(self, keep_count: int = 10) -> int:
        """
        删除最旧的备份，只保留最新的 N 条

        Args:
            keep_count: 保留数量

        Returns:
            int: 删除的行数
        """
        try:
            # 获取需要保留的 ID
            keep_stmt = (
                select(PersonaBackup.id)
                .order_by(desc(PersonaBackup.timestamp))
                .limit(keep_count)
            )
            keep_result = await self.session.execute(keep_stmt)
            keep_ids = [row[0] for row in keep_result.fetchall()]

            if not keep_ids:
                return 0

            del_stmt = delete(PersonaBackup).where(
                PersonaBackup.id.notin_(keep_ids)
            )
            del_result = await self.session.execute(del_stmt)
            await self.session.commit()
            return del_result.rowcount
        except Exception as e:
            await self.session.rollback()
            logger.error(f"[PersonaBackupRepository] 清理旧备份失败: {e}")
            return 0

    async def get_latest_backup(self) -> Optional[PersonaBackup]:
        """
        获取最新的备份

        Returns:
            Optional[PersonaBackup]: 最新的备份对象
        """
        try:
            stmt = (
                select(PersonaBackup)
                .order_by(desc(PersonaBackup.timestamp))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[PersonaBackupRepository] 获取最新备份失败: {e}")
            return None
