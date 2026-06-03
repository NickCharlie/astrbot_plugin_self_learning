"""
人格备份 Facade — 人格配置备份与恢复的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from sqlalchemy import desc, select
try:
    from ....repositories.persona_backup_repository import PersonaBackupRepository
    from ....models.orm.learning import PersonaLearningReview
    from ....models.orm.psychological import PersonaBackup
except ImportError:
    from repositories.persona_backup_repository import PersonaBackupRepository
    from models.orm.learning import PersonaLearningReview
    from models.orm.psychological import PersonaBackup


class PersonaFacade(BaseFacade):
    """人格备份管理 Facade"""

    @staticmethod
    def _json_loads(value: Any, default: Any) -> Any:
        if not value:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def _backup_to_dict(self, backup: PersonaBackup, include_content: bool = True) -> Dict[str, Any]:
        data = {
            'id': backup.id,
            'group_id': backup.group_id,
            'backup_name': backup.backup_name,
            'timestamp': backup.timestamp,
            'reason': backup.reason,
            'backup_reason': backup.backup_reason,
            'backup_time': backup.backup_time,
            'created_at': backup.created_at.isoformat() if backup.created_at else None,
        }
        if include_content:
            data.update({
                'persona_config': self._json_loads(backup.persona_config, {}),
                'original_persona': self._json_loads(backup.original_persona, {}),
                'imitation_dialogues': self._json_loads(backup.imitation_dialogues, []),
                'persona_content': backup.persona_content or '',
            })
        return data

    async def backup_persona(self, backup_data: Dict[str, Any]) -> bool:
        """创建人格备份"""
        try:
            async with self.get_session() as session:

                now = time.time()
                backup = PersonaBackup(
                    group_id=backup_data.get('group_id', 'default'),
                    backup_name=backup_data.get('backup_name', f'backup_{int(now)}'),
                    timestamp=now,
                    reason=backup_data.get('reason', ''),
                    persona_config=json.dumps(backup_data.get('persona_config', {}), ensure_ascii=False),
                    original_persona=json.dumps(backup_data.get('original_persona', {}), ensure_ascii=False),
                    imitation_dialogues=json.dumps(backup_data.get('imitation_dialogues', []), ensure_ascii=False),
                    backup_reason=backup_data.get('backup_reason', ''),
                    backup_time=now,
                    persona_content=backup_data.get('persona_content', ''),
                )
                session.add(backup)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 备份人格失败: {e}")
            return False

    async def get_persona_backups(
        self,
        group_id: Optional[str] = None,
        limit: int = 10,
        include_content: bool = False,
    ) -> List[Dict[str, Any]]:
        """获取人格备份列表"""
        try:
            async with self.get_session() as session:
                repo = PersonaBackupRepository(session)
                backups = await repo.list_backups(group_id=group_id, limit=limit)
                return [self._backup_to_dict(b, include_content=include_content) for b in backups]
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 获取备份列表失败: {e}")
            return []

    async def get_persona_backup(
        self,
        backup_id: int,
        group_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取指定备份详情"""
        try:
            async with self.get_session() as session:
                repo = PersonaBackupRepository(session)
                backup = await repo.get_backup(backup_id)
                if not backup or (group_id and backup.group_id != group_id):
                    return None
                return self._backup_to_dict(backup, include_content=True)
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 获取备份详情失败: {e}")
            return None

    async def restore_persona_backup(
        self,
        backup_id: int,
        group_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """返回指定备份内容，供上层执行实际恢复。"""
        return await self.get_persona_backup(backup_id, group_id=group_id)

    async def delete_persona_backup(
        self,
        backup_id: int,
        group_id: Optional[str] = None,
    ) -> bool:
        """删除指定人格备份"""
        try:
            async with self.get_session() as session:
                repo = PersonaBackupRepository(session)
                backup = await repo.get_backup(backup_id)
                if not backup or (group_id and backup.group_id != group_id):
                    return False
                return await repo.delete_backup(backup_id)
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 删除备份失败: {e}")
            return False

    async def get_persona_update_history(
        self, group_id: str = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取人格更新历史"""
        try:
            async with self.get_session() as session:

                stmt = select(PersonaLearningReview).order_by(
                    desc(PersonaLearningReview.timestamp)
                ).limit(limit)
                if group_id:
                    stmt = stmt.where(PersonaLearningReview.group_id == group_id)

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'timestamp': r.timestamp,
                        'group_id': r.group_id,
                        'update_type': r.update_type,
                        'status': r.status,
                        'confidence_score': r.confidence_score,
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 获取更新历史失败: {e}")
            return []
